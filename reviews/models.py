from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count


class Review(models.Model):
    """
    A rating (1-5 stars) and optional written feedback after a completed booking.

    Owners review the caregiver (#62, #63); caregivers review the owner and pet
    (#66). Each person can review a booking once.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Pet owner"
        CAREGIVER = "caregiver", "Caregiver"

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.CASCADE, related_name="reviews"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews_written",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField("Written feedback", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "author"], name="one_review_per_booking_and_author"
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_1_to_5",
            ),
        ]

    def __str__(self):
        return f"{self.rating}★ by {self.author} for booking #{self.booking_id}"

    @staticmethod
    def role_for(user, booking):
        """The role this user reviews the booking as, or None if it isn't theirs."""
        if booking.owner_id == user.pk:
            return Review.Role.OWNER
        if booking.caregiver.user_id == user.pk:
            return Review.Role.CAREGIVER
        return None


def rating_summary(reviews):
    """Average rating (one decimal) and count for a set of reviews."""
    summary = reviews.aggregate(average=Avg("rating"), count=Count("id"))
    if summary["average"] is not None:
        summary["average"] = round(summary["average"], 1)
    return summary
