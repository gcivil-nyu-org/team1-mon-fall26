from django.conf import settings
from django.db import models


class AccountProfile(models.Model):
    class Role(models.TextChoices):
        PET_OWNER = "pet_owner", "Pet Owner"
        CAREGIVER = "caregiver", "Caregiver"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_profile",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PET_OWNER,
    )

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
