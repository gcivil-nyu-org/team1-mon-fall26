from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# "Years caring for pets" is picked from ranges (Figma). The stored number is
# the start of the range, so older profiles that saved an exact number still work.
EXPERIENCE_CHOICES = [
    (0, "Less than 1 year"),
    (1, "1–2 years"),
    (3, "3–5 years"),
    (6, "6–10 years"),
    (11, "More than 10 years"),
]

# Optional pet-care skills shown on the profile (Figma "Pet-care skills").
PET_CARE_SKILLS = [
    ("giving_medication", "Giving medication"),
    ("senior_pets", "Senior pets"),
    ("puppies_kittens", "Puppies & kittens"),
    ("anxious_pets", "Anxious or reactive pets"),
    ("large_dogs", "Large dogs"),
    ("leash_training", "Leash training"),
    ("pet_first_aid", "Pet first aid"),
]


def experience_range(years):
    """The EXPERIENCE_CHOICES value that a number of years falls into."""
    return max(value for value, _ in EXPERIENCE_CHOICES if value <= max(years, 0))


class CaregiverProfile(models.Model):
    # The account that owns this profile. Lets a signed-in caregiver see and
    # respond to the booking requests sent to them.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="caregiver_profile",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    years_of_experience = models.PositiveIntegerField(default=0)
    service_area = models.CharField(max_length=150)
    # Private street address or cross street, used only to place the caregiver
    # on the map. Owners never see it; they see `neighborhood` instead.
    address = models.CharField(max_length=255, blank=True)
    # Rounded to about 100 m (see caregivers/geocoding.py).
    latitude = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    neighborhood = models.CharField(max_length=100, blank=True)
    service_radius_miles = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(25)],
        help_text="How far you're willing to travel, in miles.",
    )
    profile_photo = models.ImageField(
        upload_to="caregiver/photos", blank=True, null=True
    )
    special_skills = models.TextField(blank=True)
    certifications = models.TextField(blank=True)
    accepting_new_bookings = models.BooleanField(default=True)
    profile_creation_date = models.DateTimeField(auto_now_add=True)
    profile_creation_date = models.DateTimeField(auto_now=True)
    supported_pet_types = models.ManyToManyField("pets.PetType", blank=True)
    # Keys from PET_CARE_SKILLS.
    pet_care_skills = models.JSONField(default=list, blank=True)

    @property
    def initials(self):
        """Up to two initials for the avatar, e.g. "CS" for Chloe Shih."""
        return "".join(part[0] for part in self.name.split()[:2]).upper()

    @property
    def first_name(self):
        return self.name.split()[0] if self.name.split() else self.name

    @property
    def experience_label(self):
        """Years of experience as its range, e.g. "3–5 years"."""
        return dict(EXPERIENCE_CHOICES)[experience_range(self.years_of_experience)]

    @property
    def pet_care_skill_labels(self):
        labels = dict(PET_CARE_SKILLS)
        return [labels[key] for key in self.pet_care_skills if key in labels]


class ServiceType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

    @property
    def icon(self):
        """Which round icon the profile page shows: "walk", "home", "feeding" or "paw"."""
        name = self.name.lower()
        if any(word in name for word in ("walk", "daycare", "training")):
            return "walk"
        if any(
            word in name for word in ("drop-in", "sitting", "overnight", "boarding")
        ):
            return "home"
        if any(word in name for word in ("feeding", "medication")):
            return "feeding"
        return "paw"


class CaregiverService(models.Model):
    caregiver = models.ForeignKey("CaregiverProfile", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True, default="")
    service_type = models.ForeignKey("ServiceType", on_delete=models.CASCADE)
    PRICE_UNITS = [
        ("hour", "Per Hour"),
        ("night", "Per Night"),
        ("visit", "Per Visit / Check-in"),
        ("day", "Per Day"),
        ("walk", "Per Walk"),
    ]

    price_unit = models.CharField(max_length=10, choices=PRICE_UNITS, default="hour")
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["caregiver", "service_type"], name="unique_caregiver_service"
            )
        ]
