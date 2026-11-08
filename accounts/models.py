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

    # A pet owner's neighborhood, shown to the caregivers they message.
    # #47: filled in from the address on the owner's profile.
    neighborhood = models.CharField(max_length=100, blank=True)

    # #47: a pet owner's street address. Only they can see it; others see the
    # neighborhood above.
    address = models.CharField(max_length=255, blank=True)

    # #92: an admin can restrict an account (it can't log in or use the site)
    # and reinstate it later. Unlike deleting (#48), nothing else changes.
    restricted_at = models.DateTimeField(null=True, blank=True)
    restriction_reason = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
