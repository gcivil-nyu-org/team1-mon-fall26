from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from caregivers.models import ServiceType
from pets.models import Pet

from .models import CareOpportunity


class CareOpportunityForm(forms.ModelForm):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_clock = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_clock = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))

    class Meta:
        model = CareOpportunity
        fields = ["pet", "service_type", "location", "notes"]
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Anything your caregiver should know?",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "placeholder": "Neighborhood, city, or address",
                }
            ),
        }

    def __init__(self, *args, owner=None, lock_pet=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["pet"].queryset = (
            Pet.objects.active().filter(owner=owner)
            if owner is not None
            else Pet.objects.none()
        )
        if lock_pet and self.instance.pk:
            # Preserve the original pet even if it is no longer active.
            self.fields["pet"].queryset = Pet.objects.filter(
                pk=self.instance.pet_id, owner=owner
            )
            self.fields["pet"].disabled = True

        self.fields["service_type"].queryset = ServiceType.objects.all().order_by(
            "name"
        )

        if self.instance.pk:
            for prefix, value in (
                ("start", self.instance.start_time),
                ("end", self.instance.end_time),
            ):
                if value:
                    local_value = timezone.localtime(value)
                    self.initial[f"{prefix}_date"] = local_value.date()
                    self.initial[f"{prefix}_clock"] = local_value.time().replace(
                        tzinfo=None
                    )
        for field_name in (
            "location",
            "notes",
            "start_date",
            "start_clock",
            "end_date",
            "end_clock",
        ):
            self.fields[field_name].widget.attrs["class"] = "post-form-input"

    def clean(self):
        cleaned = super().clean()

        start_date = cleaned.get("start_date")
        start_clock = cleaned.get("start_clock")
        end_date = cleaned.get("end_date")
        end_clock = cleaned.get("end_clock")

        if not all((start_date, start_clock, end_date, end_clock)):
            return cleaned

        start = timezone.make_aware(
            timezone.datetime.combine(start_date, start_clock),
            timezone.get_current_timezone(),
        )
        end = timezone.make_aware(
            timezone.datetime.combine(end_date, end_clock),
            timezone.get_current_timezone(),
        )

        if end <= start:
            raise ValidationError("End date and time must be after the start.")

        if start <= timezone.now():
            raise ValidationError("The start date and time must be in the future.")

        cleaned["start_time"] = start
        cleaned["end_time"] = end

        return cleaned

    def save(self, commit=True):
        opportunity = super().save(commit=False)
        opportunity.start_time = self.cleaned_data["start_time"]
        opportunity.end_time = self.cleaned_data["end_time"]

        if commit:
            opportunity.save()

        return opportunity
