from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse


# Pet colors (avatars and cards). Each pet gets one from its id, so pets look
# varied but keep the same color on every page.
PET_THEMES = ("peach", "mint", "pink", "yellow", "blue", "lavender")


class Pet(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pets",
    )
    name = models.CharField(max_length=100)
    pet_type = models.ForeignKey("PetType", on_delete=models.PROTECT)
    breed = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    photo = models.ImageField(upload_to="pets/photos", blank=True, null=True)
    description = models.TextField(blank=True)
    special_care_instructions = models.TextField(blank=True)

    # Care information for caregivers (#20, #21, #23).
    # Feeding: what, how much and when, plus any extra notes.
    food = models.CharField(max_length=100, blank=True)
    portion = models.CharField(max_length=100, blank=True)
    feeding_times = models.CharField(max_length=100, blank=True)
    feeding_instructions = models.TextField("Feeding notes", blank=True)
    # Medication: name, dose and schedule. Other care notes live in
    # special_care_instructions.
    medications = models.TextField("Medication", blank=True)
    medication_dose = models.CharField("Dose", max_length=100, blank=True)
    medication_schedule = models.CharField("Schedule", max_length=100, blank=True)
    # Emergency and vet contacts.
    vet_name = models.CharField("Vet", max_length=100, blank=True)
    vet_phone = models.CharField("Vet phone", max_length=30, blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.pet_type})"

    def get_absolute_url(self):
        return reverse("pets:detail", args=[self.pk])

    @property
    def age_months(self):
        """Age in whole months, or None if no date of birth was given."""
        if not self.date_of_birth:
            return None
        today, born = date.today(), self.date_of_birth
        months = (today.year - born.year) * 12 + (today.month - born.month)
        if today.day < born.day:
            months -= 1
        return max(months, 0)

    @property
    def age_years(self):
        """Age in whole years, or None if no date of birth was given."""
        months = self.age_months
        return None if months is None else months // 12

    @property
    def age_display(self):
        """Human-friendly age, e.g. "2 years", "5 months" or "Under 1 month"."""
        months = self.age_months
        if months is None:
            return ""
        if months >= 12:
            years = months // 12
            return f"{years} year{'s' if years != 1 else ''}"
        if months == 0:
            return "Under 1 month"
        return f"{months} month{'s' if months != 1 else ''}"

    @property
    def age_short(self):
        """Compact age for small cards, e.g. "2 yrs", "1 yr" or "5 mos"."""
        months = self.age_months
        if months is None:
            return ""
        if months >= 12:
            years = months // 12
            return f"{years} yr{'s' if years != 1 else ''}"
        if months == 0:
            return "Under 1 mo"
        return f"{months} mo{'s' if months != 1 else ''}"

    @property
    def has_feeding_info(self):
        return any([self.food, self.portion, self.feeding_times, self.feeding_instructions])

    @property
    def has_medication_info(self):
        return any([self.medications, self.medication_dose, self.medication_schedule])

    @property
    def has_vet_info(self):
        return bool(self.vet_name or self.vet_phone)

    @property
    def has_emergency_contact(self):
        return bool(self.emergency_contact_name or self.emergency_contact_phone)

    @property
    def feeding_summary(self):
        """One line for caregivers, e.g. "Kibble, 1 cup at 8 AM and 6 PM."."""
        line = ", ".join(part for part in [self.food, self.portion] if part)
        if self.feeding_times:
            line = f"{line} at {self.feeding_times}" if line else self.feeding_times
        return f"{line}." if line and not line.endswith(".") else line

    @property
    def medication_summary(self):
        """One line for caregivers, e.g. "Probiotic, 1 g, once daily."."""
        line = ", ".join(
            part for part in [self.medications, self.medication_dose, self.medication_schedule] if part
        )
        return f"{line}." if line and not line.endswith(".") else line

    @property
    def theme(self):
        """CSS color theme for this pet, e.g. "mint" (see PET_THEMES)."""
        return PET_THEMES[(self.pk or 0) % len(PET_THEMES)]


class PetType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
