"""Pet-friendly places on the Explore map (stories: Use Reliable Location Data,
View Nearby Pet-Friendly Locations, View Dog Parks).

Dog parks come from NYC Parks' official "Dog Runs" dataset on NYC Open Data
(see the import_dog_runs command). NYC Open Data has no list of pet-friendly
cafés, stores or restaurants, so the PawPal team adds those in the admin. Every
place records where its information came from and when it was last checked.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse

# Longest explanation someone can add when reporting wrong information.
MAX_REPORT_LENGTH = 500


class PlaceQuerySet(models.QuerySet):
    def shown(self):
        """Places people can see: not hidden by an admin or dropped by the source."""
        return self.filter(is_active=True)


class Place(models.Model):
    class Category(models.TextChoices):
        # Labels match the Figma badges.
        DOG_PARK = "dog_park", "Dog park"
        CAFE = "cafe", "Café"
        PET_STORE = "pet_store", "Pet store"
        RESTAURANT = "restaurant", "Restaurant"

    class Source(models.TextChoices):
        NYC_PARKS = "nyc_parks", "NYC Parks on NYC Open Data"
        PAWPAL = "pawpal", "the PawPal team"

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    # Street address or cross streets, e.g. "214 7th Ave" or "Prospect Park W & 3rd St".
    address = models.CharField(max_length=200, blank=True)
    # Shown instead of the address when there is none (NYC Parks lists none).
    neighborhood = models.CharField(max_length=100, blank=True)
    borough = models.CharField(max_length=20, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    hours = models.CharField(
        max_length=80, blank=True, help_text="For example: Open daily 8 AM – 6 PM"
    )
    features = models.TextField(
        blank=True,
        help_text="What makes it pet-friendly, one per line. "
        "For example: Water bowls and treats",
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.PAWPAL
    )
    # The place's id in the source dataset, so a new import updates it.
    source_id = models.CharField(max_length=64, blank=True)
    # When the information was last checked against its source.
    checked_on = models.DateField(null=True, blank=True)
    # Unticked when an admin hides it or the source no longer lists it.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PlaceQuerySet.as_manager()

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=~Q(source_id=""),
                name="one_place_per_source_id",
            )
        ]

    def __str__(self):
        return self.name

    def feature_list(self):
        return [line.strip() for line in self.features.splitlines() if line.strip()]

    def place_line(self):
        """ "214 7th Ave, Brooklyn", or "Park Slope, Brooklyn" when there's no address."""
        parts = [p for p in (self.address or self.neighborhood, self.borough) if p]
        return ", ".join(parts)

    def directions_url(self):
        return (
            "https://www.google.com/maps/dir/?api=1&destination="
            f"{self.latitude},{self.longitude}"
        )

    def report_url(self):
        return reverse("places:report", args=[self.pk])


class PlaceReport(models.Model):
    """Someone told us a place's information is wrong ("Report wrong info")."""

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="place_reports",
    )
    details = models.TextField(max_length=MAX_REPORT_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    # Ticked by an admin once the place is fixed or the report is checked.
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.place}: {self.details[:40]}"
