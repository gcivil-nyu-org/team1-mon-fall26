from django import forms

from .models import DAYS, MAX_REPORT_LENGTH, Place, PlaceReport

BOROUGHS = ["Manhattan", "Brooklyn", "Queens", "Bronx", "The Bronx", "Staten Island"]
MAX_AMENITIES = 10
MAX_AMENITY_LENGTH = 80


def split_borough(text):
    """ "214 7th Ave, Brooklyn" -> ("214 7th Ave", "Brooklyn"); ("x", "") when
    the address doesn't end with a borough."""
    street, _, last = text.rpartition(",")
    last = last.strip()
    for borough in BOROUGHS:
        if street.strip() and last.lower() == borough.lower():
            return street.strip(), "Bronx" if borough == "The Bronx" else borough
    return text.strip(), ""


def address_line(place):
    """The address as the edit form shows it: "214 7th Ave, Brooklyn"."""
    return place.place_line() if place.address else ""


class PlaceForm(forms.Form):
    """Figma "Manage Pet-Friendly Location (Edit)": name, type, address,
    day-by-day hours and pet amenities."""

    name = forms.CharField(
        max_length=150,
        error_messages={"required": "Add a name."},
    )
    category = forms.ChoiceField(
        label="Type",
        choices=Place.Category.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Pick a type."},
    )
    address = forms.CharField(
        max_length=200,
        error_messages={"required": "Add an address."},
        widget=forms.TextInput(attrs={"placeholder": "e.g. 214 7th Ave, Brooklyn"}),
    )

    def __init__(self, *args, place, amenities=None, **kwargs):
        self.place = place
        hours = place.weekly_hours or [None] * len(DAYS)
        initial = {
            "name": place.name,
            "category": place.category,
            "address": address_line(place),
        }
        for day, day_hours in zip(DAYS, hours):
            key = day.lower()
            initial[f"{key}_open"] = bool(day_hours)
            initial[f"{key}_from"] = day_hours["open"] if day_hours else "09:00"
            initial[f"{key}_to"] = day_hours["close"] if day_hours else "17:00"
        super().__init__(*args, initial=initial, **kwargs)
        # Category order follows the Figma chips, then the types added since.
        # Every type needs a chip, or places of that type can't be saved.
        self.fields["category"].choices = [
            (Place.Category.CAFE, "Café"),
            (Place.Category.DOG_PARK, "Dog park"),
            (Place.Category.PET_STORE, "Pet store"),
            (Place.Category.RESTAURANT, "Restaurant"),
            (Place.Category.OUTDOOR_DINING, "Outdoor dining"),
            (Place.Category.OFF_LEASH, "Off-leash area"),
            (Place.Category.DOG_FOUNTAIN, "Dog fountain"),
        ]
        for day in DAYS:
            key = day.lower()
            self.fields[f"{key}_open"] = forms.BooleanField(required=False)
            for part in ("from", "to"):
                self.fields[f"{key}_{part}"] = forms.TimeField(
                    required=False,
                    input_formats=["%H:%M", "%H:%M:%S"],
                    widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
                    error_messages={"invalid": "Use a time like 8:00 AM."},
                )
        if amenities is None:
            amenities = place.feature_list()
        self.amenities = [a.strip() for a in amenities if a.strip()]

    def days(self):
        """One row per day for the template: label and its three fields."""
        return [
            {
                "name": day,
                "open": self[f"{day.lower()}_open"],
                "from": self[f"{day.lower()}_from"],
                "to": self[f"{day.lower()}_to"],
                "errors": self.errors.get(f"{day.lower()}_from"),
            }
            for day in DAYS
        ]

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_address(self):
        return self.cleaned_data["address"].strip()

    def clean(self):
        cleaned = super().clean()
        for day in DAYS:
            key = day.lower()
            if not cleaned.get(f"{key}_open"):
                continue
            opens, closes = cleaned.get(f"{key}_from"), cleaned.get(f"{key}_to")
            if f"{key}_from" in self.errors or f"{key}_to" in self.errors:
                continue
            if opens is None or closes is None:
                self.add_error(f"{key}_from", "Add when it opens and closes.")
            elif opens == closes:
                self.add_error(f"{key}_from", "Opening and closing can't match.")
        if len(self.amenities) > MAX_AMENITIES:
            self.add_error(None, f"Keep it to {MAX_AMENITIES} amenities.")
        if any(len(a) > MAX_AMENITY_LENGTH for a in self.amenities):
            self.add_error(
                None, f"Keep each amenity under {MAX_AMENITY_LENGTH} characters."
            )
        return cleaned

    def weekly_hours(self):
        """The hours to save: [] when no day is switched on (hours not listed)."""
        days = []
        for day in DAYS:
            key = day.lower()
            if self.cleaned_data.get(f"{key}_open"):
                days.append(
                    {
                        "open": self.cleaned_data[f"{key}_from"].strftime("%H:%M"),
                        "close": self.cleaned_data[f"{key}_to"].strftime("%H:%M"),
                    }
                )
            else:
                days.append(None)
        return days if any(days) else []

    def address_changed(self):
        return self.cleaned_data["address"] != address_line(self.place)


class PlaceReportForm(forms.ModelForm):
    """Figma "Report wrong info": what's wrong, and details."""

    reason = forms.ChoiceField(
        label="What's wrong?",
        choices=PlaceReport.Reason.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Pick what's wrong."},
    )
    details = forms.CharField(
        label="Details",
        max_length=MAX_REPORT_LENGTH,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "maxlength": MAX_REPORT_LENGTH,
                "placeholder": "For example: it closes at 5 PM now",
            }
        ),
        error_messages={
            "required": "Tell us what's wrong so we can fix it.",
            "max_length": f"Keep it to {MAX_REPORT_LENGTH} characters.",
        },
    )

    class Meta:
        model = PlaceReport
        fields = ["reason", "details"]
