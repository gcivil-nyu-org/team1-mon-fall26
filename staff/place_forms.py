"""#107: correct a pet-friendly place's information (Figma "Manage
Pet-Friendly Location Information (Edit)")."""

from django import forms

from caregivers.geocoding import GeocodingUnavailable, geocode
from places.models import Place


class PlaceForm(forms.ModelForm):
    class Meta:
        model = Place
        fields = [
            "name",
            "category",
            "address",
            "neighborhood",
            "borough",
            "zip_code",
            "hours",
            "features",
        ]
        labels = {
            "neighborhood": "Cross streets or area",
            "zip_code": "ZIP code",
            "features": "Pet amenities",
        }
        help_texts = {
            "hours": "For example: 8 AM – 6 PM",
            "features": "One per line, for example: Water bowls and treats",
        }
        widgets = {"features": forms.Textarea(attrs={"rows": 3})}
        error_messages = {"name": {"required": "Enter the place's name."}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location = None
        # Set when GeoSearch can't be reached: the details still save.
        self.geocoding_unavailable = False

    def clean(self):
        cleaned = super().clean()
        for field in (
            "name",
            "address",
            "neighborhood",
            "borough",
            "zip_code",
            "hours",
        ):
            if isinstance(cleaned.get(field), str):
                cleaned[field] = cleaned[field].strip()
        address = cleaned.get("address", "")
        if not address and not cleaned.get("neighborhood"):
            self.add_error("address", "Add an address or the cross streets.")
        elif address and address != self.instance.address:
            # A new address moves the pin on the Explore map.
            try:
                self.location = geocode(
                    ", ".join(
                        part for part in (address, cleaned.get("borough")) if part
                    )
                )
            except GeocodingUnavailable:
                self.geocoding_unavailable = True
            else:
                if self.location is None:
                    self.add_error(
                        "address",
                        "We couldn't find this address in New York City. "
                        "Check the house number and street name.",
                    )
        return cleaned

    def save(self, commit=True):
        place = super().save(commit=False)
        if self.location is not None:
            place.latitude = self.location.latitude
            place.longitude = self.location.longitude
        if commit:
            place.save()
        return place
