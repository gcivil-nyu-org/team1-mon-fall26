import re
from datetime import date

from django import forms
from django.db.models import Case, IntegerField, Value, When

from .models import TEMPERAMENT_TRAITS, Pet, PetType

# Pet types appear as chips in this order; any others follow alphabetically,
# and "Other" always comes last.
CHIP_ORDER = ["Dog", "Cat", "Bird", "Rabbit", "Fish"]

MAX_AGE = {"years": 50, "months": 600}
MAX_PHOTO_MB = 5

# Digits plus the usual separators: "(212) 555-0142", "+1 212.555.0142".
PHONE_CHARS = re.compile(r"^[0-9+().\-\s]+$")
PHONE_ERROR = "Enter a phone number with 7 to 15 digits, e.g. (212) 555-0142."


def pet_type_choices():
    order = [When(name=name, then=Value(i)) for i, name in enumerate(CHIP_ORDER)]
    order.append(When(name="Other", then=Value(1000)))
    return PetType.objects.annotate(
        chip_order=Case(*order, default=Value(500), output_field=IntegerField())
    ).order_by("chip_order", "name")


def subtract_months(day, months):
    """Return the date `months` months before `day` (clamped to month end)."""
    month_index = day.year * 12 + (day.month - 1) - months
    year, month = divmod(month_index, 12)
    month += 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return date(year, month, candidate)
        except ValueError:
            continue


class PetForm(forms.ModelForm):
    """


    Age is stored as an approximate date of birth, so a pet's age stays
    correct over time without the owner having to update it.
    """

    pet_type = forms.ModelChoiceField(
        queryset=PetType.objects.none(),
        widget=forms.RadioSelect,
        empty_label=None,
        label="Type of pet",
        error_messages={
            "required": "Choose or enter a pet type.",
            "invalid_choice": "Choose or enter a pet type.",
        },
    )
    age = forms.IntegerField(
        min_value=0,
        label="Age",
        widget=forms.NumberInput(attrs={"placeholder": "0", "min": 0}),
        error_messages={
            "required": "Enter your pet's age as a number.",
            "invalid": "Enter your pet's age as a number.",
            "min_value": "Age can't be negative.",
        },
    )
    age_unit = forms.ChoiceField(
        choices=[("years", "years"), ("months", "months")],
        initial="years",
        label="Age unit",
    )
    remove_photo = forms.BooleanField(required=False, label="Remove photo")
    temperament_traits = forms.MultipleChoiceField(
        choices=TEMPERAMENT_TRAITS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Temperament",
    )

    class Meta:
        model = Pet
        fields = [
            "photo",
            "name",
            "pet_type",
            "food",
            "portion",
            "feeding_times",
            "feeding_instructions",
            "temperament_traits",
            "behavior_notes",
            "medications",
            "medication_dose",
            "medication_schedule",
            "special_care_instructions",
            "vet_name",
            "vet_phone",
            "emergency_contact_name",
            "emergency_contact_phone",
        ]
        labels = {
            "photo": "Photo",
            "name": "Pet name",
            "food": "Food",
            "portion": "Portion",
            "feeding_times": "Feeding times",
            "feeding_instructions": "Feeding notes",
            "medications": "Medication",
            "medication_dose": "Dose",
            "medication_schedule": "Schedule",
            "special_care_instructions": "Special care instructions",
            "behavior_notes": "Behavior notes & preferences",
            "vet_name": "Vet name & clinic",
            "vet_phone": "Vet phone",
            "emergency_contact_name": "Emergency contact",
            "emergency_contact_phone": "Emergency phone",
        }
        widgets = {
            "photo": forms.FileInput(attrs={"accept": "image/*"}),
            "name": forms.TextInput(attrs={"placeholder": "e.g. Pepper"}),
            "food": forms.TextInput(
                attrs={"placeholder": "e.g. Timothy hay, kibble brand"}
            ),
            "portion": forms.TextInput(attrs={"placeholder": "e.g. 1 cup"}),
            "feeding_times": forms.TextInput(
                attrs={"placeholder": "e.g. 8:00 AM, 6:00 PM"}
            ),
            "feeding_instructions": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Treats, water, foods to avoid"}
            ),
            # One line in the design, but kept as a text field so longer names fit.
            "medications": forms.TextInput(attrs={"placeholder": "e.g. Probiotic"}),
            "medication_dose": forms.TextInput(attrs={"placeholder": "e.g. 1 g"}),
            "medication_schedule": forms.TextInput(
                attrs={"placeholder": "e.g. Once daily with breakfast"}
            ),
            "behavior_notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "e.g. Loves belly rubs. Nervous around bikes, so keep the leash short.",
                }
            ),
            "special_care_instructions": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Handling, health conditions, routines",
                }
            ),
            "vet_name": forms.TextInput(
                attrs={"placeholder": "e.g. Dr. Patel, Brooklyn Vets"}
            ),
            "vet_phone": forms.TextInput(
                attrs={"placeholder": "(000) 000-0000", "type": "tel"}
            ),
            "emergency_contact_name": forms.TextInput(
                attrs={"placeholder": "Name and relationship"}
            ),
            "emergency_contact_phone": forms.TextInput(
                attrs={"placeholder": "(000) 000-0000", "type": "tel"}
            ),
        }
        error_messages = {
            "name": {"required": "Enter your pet's name."},
            "photo": {
                "invalid_image": "Upload a photo in JPG, PNG, GIF or WebP format."
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pet_type"].queryset = pet_type_choices()

        # When editing, show the saved birth date as an age again.
        pet = self.instance
        if pet.pk and pet.date_of_birth and not self.is_bound:
            years = pet.age_years
            if years >= 1:
                self.initial.update(age=years, age_unit="years")
            else:
                self.initial.update(age=pet.age_months, age_unit="months")

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"Photo must be smaller than {MAX_PHOTO_MB} MB."
            )
        return photo

    def _clean_phone(self, field):
        phone = self.cleaned_data.get(field, "").strip()
        if phone:
            digits = re.sub(r"\D", "", phone)
            if not PHONE_CHARS.match(phone) or not 7 <= len(digits) <= 15:
                raise forms.ValidationError(PHONE_ERROR)
        return phone

    def clean_vet_phone(self):
        return self._clean_phone("vet_phone")

    def clean_emergency_contact_phone(self):
        return self._clean_phone("emergency_contact_phone")

    def clean(self):
        cleaned = super().clean()
        age = cleaned.get("age")
        unit = cleaned.get("age_unit")
        if age is not None and unit and age > MAX_AGE[unit]:
            self.add_error("age", f"Enter an age of {MAX_AGE[unit]} {unit} or less.")

        # A name without a number (or the reverse) is no use in an emergency.
        pairs = [
            ("vet_name", "vet_phone", "Add the vet's phone number too."),
            (
                "emergency_contact_name",
                "emergency_contact_phone",
                "Add a phone number for your emergency contact.",
            ),
        ]
        for name_field, phone_field, message in pairs:
            if (
                cleaned.get(name_field)
                and not cleaned.get(phone_field)
                and phone_field not in self.errors
            ):
                self.add_error(phone_field, message)
        if cleaned.get("emergency_contact_phone") and not cleaned.get(
            "emergency_contact_name"
        ):
            self.add_error(
                "emergency_contact_name", "Add your emergency contact's name."
            )
        if (
            cleaned.get("medication_dose") or cleaned.get("medication_schedule")
        ) and not cleaned.get("medications"):
            self.add_error("medications", "Add the medication's name.")
        return cleaned

    def save(self, commit=True):
        age = self.cleaned_data["age"]
        months = age * 12 if self.cleaned_data["age_unit"] == "years" else age
        self.instance.date_of_birth = subtract_months(date.today(), months)

        # "Remove photo" only applies when no new photo was chosen.
        new_photo = self.add_prefix("photo") in self.files
        if self.cleaned_data.get("remove_photo") and not new_photo:
            if self.instance.photo:
                self.instance.photo.delete(save=False)
            self.instance.photo = None
        return super().save(commit=commit)
