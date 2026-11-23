from django.conf import settings
from django.db import models
from django.utils import dateformat, timezone


def _when(value, fmt):
    """`value` in local time; the year is added when it isn't this year (#331)."""
    local = timezone.localtime(value)
    if local.year != timezone.localdate().year:
        fmt = fmt.replace("M j", "M j, Y", 1)
    return dateformat.format(local, fmt)


class CareOpportunityQuerySet(models.QuerySet):
    def upcoming(self):
        """Posts whose care hasn't started yet: caregivers can still offer
        to help (#298, #325, #346)."""
        return self.filter(start_time__gt=timezone.now())


class CareOpportunity(models.Model):

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="care_opportunities",
    )

    pet = models.ForeignKey(
        "pets.Pet",
        on_delete=models.PROTECT,
        related_name="care_opportunities",
    )

    service_type = models.ForeignKey(
        "caregivers.ServiceType",
        on_delete=models.PROTECT,
        related_name="care_opportunities",
    )
    start_time = models.DateTimeField()

    end_time = models.DateTimeField()

    location = models.CharField(max_length=255)

    notes = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    objects = CareOpportunityQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="opportunity_end_after_start",
            )
        ]

    def __str__(self):
        return f"Care Opportunity #{self.pk} ({self.get_status_display()})"

    @property
    def has_started(self):
        return self.start_time <= timezone.now()

    def time_range(self):
        """ "Wed, Nov 25 · 2:00 PM – 3:00 PM", with the end date when the care
        runs into another day (#301)."""
        start = timezone.localtime(self.start_time)
        end = timezone.localtime(self.end_time)
        first = _when(start, "D, M j · g:i A")
        if start.date() == end.date():
            return f"{first} – {dateformat.format(end, 'g:i A')}"
        return f"{first} – {_when(end, 'D, M j · g:i A')}"


class CareOpportunityInterest(models.Model):
    """One caregiver's current or previously withdrawn interest in a care post."""

    opportunity = models.ForeignKey(
        CareOpportunity, on_delete=models.CASCADE, related_name="interests"
    )
    caregiver = models.ForeignKey(
        "caregivers.CaregiverProfile",
        on_delete=models.CASCADE,
        related_name="opportunity_interests",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opportunity", "caregiver"],
                name="unique_caregiver_opportunity_interest",
            )
        ]

    def __str__(self):
        return (
            f"{self.caregiver_id} interested in {self.opportunity_id}: {self.is_active}"
        )
