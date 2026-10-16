from django import forms
from django.utils import timezone

from caregivers.models import CaregiverProfile, CaregiverService

from .models import Booking

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


def offered_service_type_ids(caregiver):
    """IDs of the service types a caregiver currently offers."""
    return set(
        CaregiverService.objects.filter(
            caregiver=caregiver, is_active=True
        ).values_list("service_type_id", flat=True)
    )


class BookingRequestForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["pet", "caregiver", "service_type", "start_time", "end_time", "notes"]
        labels = {
            "service_type": "Requested service",
            "start_time": "Start",
            "end_time": "End",
            "notes": "Request details",
        }
        widgets = {
            "start_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT
            ),
            "end_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT
            ),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["caregiver"].queryset = CaregiverProfile.objects.filter(
            accepting_new_bookings=True
        ).order_by("name")
        # Readable dropdown labels without touching the other apps' models.
        self.fields["pet"].label_from_instance = lambda pet: pet.name
        self.fields["caregiver"].label_from_instance = lambda cg: cg.name
        self.fields["service_type"].label_from_instance = lambda st: st.name
        for name in ("start_time", "end_time"):
            self.fields[name].input_formats = [DATETIME_FORMAT]

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
            # Only enforce once the caregiver has listed services.
            if offered and service_type.pk not in offered:
                self.add_error(
                    "service_type", "This caregiver does not offer that service."
                )
        return cleaned
