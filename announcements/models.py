"""Platform announcements (story: As an administrator, I want to post platform
announcements so that users are informed about important updates, policy
changes, or outages). Laid out like Kat's "PawPal - Announcements" Figma."""

from django.conf import settings
from django.db import models
from django.db.models import Q

MAX_TITLE_LENGTH = 120
MAX_MESSAGE_LENGTH = 500


class AnnouncementQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Announcement.Status.PUBLISHED)

    def drafts(self):
        return self.filter(status=Announcement.Status.DRAFT)

    def for_user(self, user):
        """Published announcements this user should see, newest first:
        everyone's, plus those for pet owners or for caregivers."""
        audience = (
            Announcement.Audience.CAREGIVERS
            if is_caregiver(user)
            else Announcement.Audience.PET_OWNERS
        )
        return (
            self.published()
            .filter(Q(audience=Announcement.Audience.EVERYONE) | Q(audience=audience))
            .order_by("-published_at", "-pk")
        )


def is_caregiver(user):
    """Same rule as the header: anyone who signed up as a caregiver, even
    before they make their caregiver profile."""
    if hasattr(user, "caregiver_profile"):
        return True
    profile = getattr(user, "account_profile", None)
    return bool(profile and profile.role == "caregiver")


class Announcement(models.Model):
    class Kind(models.TextChoices):
        UPDATE = "update", "Update"
        POLICY = "policy", "Policy"
        MAINTENANCE = "maintenance", "Maintenance"

    class Audience(models.TextChoices):
        EVERYONE = "everyone", "Everyone"
        PET_OWNERS = "pet_owners", "Pet owners"
        CAREGIVERS = "caregivers", "Caregivers"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=MAX_TITLE_LENGTH)
    # A draft can be saved before these are picked; publishing needs all of them.
    kind = models.CharField(max_length=20, choices=Kind.choices, blank=True)
    audience = models.CharField(max_length=20, choices=Audience.choices, blank=True)
    message = models.TextField(max_length=MAX_MESSAGE_LENGTH, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    objects = AnnouncementQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-updated_at", "-pk"]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED


class AnnouncementDismissal(models.Model):
    """Someone closed the banner, so it stops showing for them."""

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="dismissals"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dismissed_announcements",
    )
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"], name="one_dismissal_per_user"
            )
        ]
