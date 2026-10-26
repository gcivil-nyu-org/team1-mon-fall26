from django import forms
from django.utils import timezone

from caregivers.models import CaregiverProfile, CaregiverService, ServiceType
from pets.models import Pet

from .models import Booking

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
    """Lets a signed-in owner request care for one of their own pets."""

    pet = forms.ModelChoiceField(
        queryset=Pet.objects.none(),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Which pet needs care?",
        error_messages={
            "required": "Choose one of your pets.",
            "invalid_choice": "Choose one of your pets.",
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
        fields = ["pet", "caregiver", "service_type", "start_time", "end_time", "notes"]
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
        self.fields["pet"].queryset = Pet.objects.filter(owner=owner).select_related(
            "pet_type"
        )
        # Owners can't send a request to their own caregiver profile.
        self.fields["caregiver"].queryset = (
            CaregiverProfile.objects.filter(accepting_new_bookings=True)
            .exclude(user=owner)
            .order_by("name")
        )
        self.fields["service_type"].queryset = ServiceType.objects.order_by("name")

        # Readable choice labels without touching the other apps' models.
        self.fields["pet"].label_from_instance = lambda pet: pet.name
        self.fields["caregiver"].label_from_instance = (
            lambda cg: f"{cg.name} · {cg.service_area}" if cg.service_area else cg.name
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

    def clean_start_time(self):
        start = self.cleaned_data["start_time"]
        if start <= timezone.now():
            raise forms.ValidationError("Start time must be in the future.")
        return start

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "End time must be after the start time.")

        caregiver = cleaned.get("caregiver")
        service_type = cleaned.get("service_type")
        if caregiver and service_type:
            offered = offered_service_type_ids(caregiver)
            # Only enforce once the caregiver has listed their services.
            if offered and service_type.pk not in offered:
                self.add_error(
                    "service_type", "This caregiver doesn't offer that service."
                )
        return cleaned
