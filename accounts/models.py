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

    # Sign-up email verification. New sign-ups start unverified and can't log
    # in until they click the link we email them (or reset their password,
    # which also proves they own the email). Accounts made before this, and
    # ones made by an admin, count as verified.
    email_verified = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
