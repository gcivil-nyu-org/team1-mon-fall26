from django import forms

from .geocoding import GeocodingUnavailable, geocode
from .models import (
    EXPERIENCE_CHOICES,
    PET_CARE_SKILLS,
    CaregiverProfile,
    CaregiverService,
    ServiceType,
    experience_range,
    CaregiverAvailability,
)


class CaregiverProfileForm(forms.ModelForm):
    # Saved together as the profile's `name`.
    first_name = forms.CharField(max_length=50, label="First name")
    last_name = forms.CharField(max_length=50, label="Last name")
    selected_services = forms.ModelMultipleChoiceField(
        queryset=ServiceType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    # Shown as a dropdown of ranges; any whole number is accepted and saved as
    # the start of its range (e.g. 4 is saved as 3, "3–5 years").
    years_of_experience = forms.IntegerField(
        min_value=0,
        initial=0,
        label="Years caring for pets",
        widget=forms.Select(choices=EXPERIENCE_CHOICES),
    )
    pet_care_skills = forms.MultipleChoiceField(
        choices=PET_CARE_SKILLS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = CaregiverProfile
        # `name` comes from first and last name, and `service_area` from the
        # neighborhood NYC GeoSearch finds for the address.
        fields = [
            "bio",
            "years_of_experience",
            "address",
            "service_radius_miles",
            "profile_photo",
            "special_skills",
            "certifications",
            "supported_pet_types",
            "pet_care_skills",
            "accepting_new_bookings",
        ]
        widgets = {
            "supported_pet_types": forms.CheckboxSelectMultiple(
                attrs={"class": "pet-checkbox"}
            ),
            "bio": forms.Textarea(attrs={"rows": 3}),
            "special_skills": forms.Textarea(attrs={"rows": 3}),
            "certifications": forms.Textarea(attrs={"rows": 3}),
            "address": forms.TextInput(
                attrs={"placeholder": "e.g. 70 Washington Square South"}
            ),
        }
        labels = {
            "address": "Address",
            "service_radius_miles": "Max travel distance (miles)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Required for new entries; the model allows blank so older profiles
        # without an address still load.
        self.fields["address"].required = True
        if self.instance.pk and self.instance.name:
            first, _, last = self.instance.name.partition(" ")
            self.initial.setdefault("first_name", first)
            self.initial.setdefault("last_name", last)
        # Older profiles saved an exact number of years; show the range it falls in.
        if self.instance.pk:
            self.initial["years_of_experience"] = experience_range(
                self.instance.years_of_experience
            )
        # Set when the address lookup service is down: the profile still saves,
        # without map coordinates, and the view tells the caregiver.
        self.geocoding_unavailable = False
        self._location = None

    def clean_years_of_experience(self):
        return experience_range(self.cleaned_data["years_of_experience"])

    @property
    def matched_location(self):
        """The Location found for a new or changed address, if any."""
        return self._location

    def clean_address(self):
        address = self.cleaned_data["address"].strip()
        instance = self.instance
        unchanged = (
            instance.pk
            and address == instance.address
            and instance.latitude is not None
        )
        if unchanged:
            return address
        try:
            self._location = geocode(address)
        except GeocodingUnavailable:
            self.geocoding_unavailable = True
            return address
        if self._location is None:
            raise forms.ValidationError(
                "We couldn't find this address in New York City. "
                "Check the house number and street name."
            )
        return address

    def save(self, commit=True):
        caregiver = super().save(commit=False)
        caregiver.name = " ".join(
            part
            for part in (
                self.cleaned_data["first_name"].strip(),
                self.cleaned_data["last_name"].strip(),
            )
            if part
        )
        if self._location is not None:
            caregiver.latitude = self._location.latitude
            caregiver.longitude = self._location.longitude
            caregiver.neighborhood = self._location.neighborhood
            # Shown to owners, e.g. "Park Slope, Brooklyn".
            caregiver.service_area = ", ".join(
                part
                for part in (self._location.neighborhood, self._location.borough)
                if part
            )
        elif self.geocoding_unavailable:
            # Don't keep coordinates that belong to an old address.
            caregiver.latitude = caregiver.longitude = None
            caregiver.neighborhood = ""
        if commit:
            caregiver.save()
            self.save_m2m()
        return caregiver


class CaregiverServicesForm(forms.ModelForm):
    class Meta:
        model = CaregiverService
        fields = ["service_type", "price_unit", "price", "description", "is_active"]
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Tell pet owners what's included in this service...",
                }
            ),
            "price": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "placeholder": "e.g. 25.00"}
            ),
        }

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price < 0:
            raise forms.ValidationError("Price can't be negative.")
        return price


class CaregiverAvailabilityForm(forms.ModelForm):
    class Meta:
        model = CaregiverAvailability
        fields = ["date", "start_time", "end_time"]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "start_time": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
            "end_time": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
        }
