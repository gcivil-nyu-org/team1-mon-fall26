from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


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
    def theme(self):
        """CSS color theme for this pet's type, e.g. "dog" or "rabbit"."""
        return slugify(self.pet_type.name) if self.pet_type_id else "other"


class PetType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
