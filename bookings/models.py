from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

# Accepted care the caregiver didn't mark as completed is completed this long after it ends.
AUTO_COMPLETE_AFTER = timedelta(hours=24)


class Booking(models.Model):
    """A pet owner's request for care from a caregiver."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Canceled"
        COMPLETED = "completed", "Completed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    pet = models.ForeignKey(
        "pets.Pet", on_delete=models.PROTECT, related_name="bookings"
    )
    caregiver = models.ForeignKey(
        "caregivers.CaregiverProfile",
        on_delete=models.PROTECT,
        related_name="booking_requests",
    )
    service_type = models.ForeignKey(
        "caregivers.ServiceType", on_delete=models.PROTECT, related_name="bookings"
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="booking_end_after_start",
            )
        ]

    def __str__(self):
        return f"Booking #{self.pk} ({self.get_status_display()})"

    def get_absolute_url(self):
        return reverse("bookings:booking_detail", args=[self.pk])

    @property
    def shows_pet_care_info(self):
        """Accepted and not over yet: the caregiver can see the pet's full profile."""
        return self.status == self.Status.ACCEPTED and self.end_time > timezone.now()

    @property
    def shows_emergency_contacts(self):
        """Emergency and vet contacts are only shared while the care is happening."""
        now = timezone.now()
        return (
            self.status == self.Status.ACCEPTED and self.start_time <= now < self.end_time
        )

    @property
    def completed_automatically(self):
        """True if PawPal completed it, not the caregiver (see complete_overdue)."""
        return (
            self.status == self.Status.COMPLETED
            and self.updated_at == self.end_time + AUTO_COMPLETE_AFTER
        )

    @classmethod
    def decline_expired(cls):
        """Pending requests nobody answered before their start time become Declined."""
        now = timezone.now()
        return cls.objects.filter(status=cls.Status.PENDING, start_time__lte=now).update(
            status=cls.Status.DECLINED, updated_at=now
        )

    @classmethod
    def complete_overdue(cls):
        """Accepted care not marked as completed within AUTO_COMPLETE_AFTER of ending
        becomes Completed. updated_at is set to exactly that moment, which is how
        completed_automatically tells it apart from the caregiver's own click."""
        return cls.objects.filter(
            status=cls.Status.ACCEPTED,
            end_time__lte=timezone.now() - AUTO_COMPLETE_AFTER,
        ).update(status=cls.Status.COMPLETED, updated_at=F("end_time") + AUTO_COMPLETE_AFTER)

    @classmethod
    def update_overdue(cls):
        """Run both time-based status changes before showing bookings."""
        cls.decline_expired()
        cls.complete_overdue()
