from datetime import timedelta

from django import forms
from django.utils import timezone

from caregivers.models import CaregiverProfile, CaregiverService, ServiceType
from pets.models import Pet

from .availability import covered_by_availability
from .models import Booking

# How far ahead care can be requested, and the longest one request can run
# (#331, #332): a typo can't make a request for the year 2140 or 9999.
MAX_DAYS_AHEAD = 365
MAX_LENGTH = timedelta(days=30)

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


def date_and_time_field(when):
    """A start or end time entered as two boxes: a date picker and a time picker."""
    return forms.SplitDateTimeField(
        input_date_formats=[DATE_FORMAT],
        input_time_formats=[TIME_FORMAT],
        # Lets a half-filled time say what's missing instead of "Choose when…".
        require_all_fields=False,
        widget=forms.SplitDateTimeWidget(
            date_attrs={"type": "date"},
            time_attrs={"type": "time"},
            date_format=DATE_FORMAT,
            time_format=TIME_FORMAT,
        ),
        error_messages={
            "required": f"Choose when care should {when}.",
            "incomplete": "Choose both a date and a time.",
            "invalid_date": "Enter a valid date.",
            "invalid_time": "Enter a valid time.",
        },
    )


def offered_service_type_ids(caregiver):
    """IDs of the service types a caregiver currently offers."""
    return set(
        CaregiverService.objects.filter(
            caregiver=caregiver, is_active=True
        ).values_list("service_type_id", flat=True)
    )


class BookingRequestForm(forms.ModelForm):
    """Lets a signed-in owner request care for one or more of their own pets.
    With several pets, the caregiver works out the price."""

    pets = forms.ModelMultipleChoiceField(
        queryset=Pet.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Which pets need care?",
        error_messages={
            "required": "Choose at least one of your pets.",
            "invalid_choice": "Choose your own pets.",
            "invalid_pk_value": "Choose your own pets.",
        },
    )
    caregiver = forms.ModelChoiceField(
        queryset=CaregiverProfile.objects.none(),
        empty_label="Choose a caregiver",
        label="Caregiver",
        error_messages={
            "required": "Choose a caregiver.",
            "invalid_choice": "This caregiver isn't taking new bookings.",
        },
    )
    service_type = forms.ModelChoiceField(
        queryset=ServiceType.objects.none(),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Service",
        error_messages={
            "required": "Choose a service.",
            "invalid_choice": "Choose a service.",
        },
    )
    start_time = date_and_time_field("start")
    end_time = date_and_time_field("end")

    class Meta:
        model = Booking
        fields = ["caregiver", "service_type", "start_time", "end_time", "notes"]
        labels = {"notes": "Note for the caregiver"}
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Anything specific about this visit",
                }
            ),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.fields["pets"].queryset = (
            Pet.objects.active()
            .filter(owner=owner)
            .select_related("pet_type")
            .order_by("name", "pk")
        )
        # Owners can't send a request to their own caregiver profile.
        self.fields["caregiver"].queryset = (
            CaregiverProfile.objects.filter(accepting_new_bookings=True)
            .exclude(user=owner)
            .order_by("name")
        )
        self.fields["service_type"].queryset = ServiceType.objects.order_by("name")

        # Readable choice labels without touching the other apps' models.
        self.fields["pets"].label_from_instance = lambda pet: pet.name
        self.fields["caregiver"].label_from_instance = lambda cg: (
            f"{cg.name} · {cg.service_area}" if cg.service_area else cg.name
        )
        self.fields["service_type"].label_from_instance = lambda st: st.name
        # The date pickers start at today.
        today = timezone.localdate().strftime(DATE_FORMAT)
        for name in ("start_time", "end_time"):
            self.fields[name].widget.widgets[0].attrs["min"] = today

    def services_by_caregiver(self):
        """{caregiver id: [service type ids]} so the page can show only what each
        caregiver offers. Caregivers with nothing listed yet aren't included, and
        all services are shown for them (the same rule clean() uses)."""
        offered = {}
        rows = CaregiverService.objects.filter(
            caregiver__in=self.fields["caregiver"].queryset, is_active=True
        ).values_list("caregiver_id", "service_type_id")
        for caregiver_id, service_type_id in rows:
            offered.setdefault(caregiver_id, []).append(service_type_id)
        return offered

    def save(self, commit=True):
        """The first pet picked becomes the booking's `pet`; all go in `pets`."""
        booking = super().save(commit=False)
        booking.pet = self.cleaned_data["pets"][0]
        if commit:
            booking.save()
            self.save_m2m()
        return booking

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.pets.set(self.cleaned_data["pets"])

    def clean_start_time(self):
        start = self.cleaned_data["start_time"]
        if start <= timezone.now():
            raise forms.ValidationError("Start time must be in the future.")
        if start > timezone.now() + timedelta(days=MAX_DAYS_AHEAD):
            raise forms.ValidationError("Choose a start date within the next year.")
        return start

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "End time must be after the start time.")
            end = None
        elif start and end and end - start > MAX_LENGTH:
            self.add_error("end_time", "One request can cover up to 30 days of care.")
            end = None

        caregiver = cleaned.get("caregiver")
        service_type = cleaned.get("service_type")
        if caregiver and service_type:
            offered = offered_service_type_ids(caregiver)
            # Owners can only request services the caregiver lists (#297).
            if not offered:
                self.add_error(
                    "service_type", "This caregiver hasn't listed any services yet."
                )
            elif service_type.pk not in offered:
                self.add_error(
                    "service_type", "This caregiver doesn't offer that service."
                )

        if caregiver and start and end and "start_time" not in self.errors:
            # Only time the caregiver opened on their calendar (#297, #307).
            if not covered_by_availability(caregiver, start, end):
                self.add_error(
                    "start_time",
                    f"{caregiver.name} isn't available then. "
                    "Pick one of their open times on their profile.",
                )
            elif self._duplicate(caregiver, start, end):
                # The same request again (#312): point to the one already sent.
                self.add_error(
                    None,
                    "You already have a request with this caregiver at this time. "
                    "Check My requests.",
                )
        return cleaned

    def _duplicate(self, caregiver, start, end):
        return Booking.objects.filter(
            owner=self.owner,
            caregiver=caregiver,
            status__in=[Booking.Status.PENDING, Booking.Status.ACCEPTED],
            start_time__lt=end,
            end_time__gt=start,
        ).exists()
