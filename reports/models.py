"""Reports of inappropriate content (story #117, Report Content epic).

A pet owner or caregiver can report a review or a message they received. The
report keeps a copy of the reported text, so admins still see what was said if
the review or message is later removed.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

# Longest explanation someone can add to a report.
MAX_DETAILS_LENGTH = 500


class Report(models.Model):
    class Kind(models.TextChoices):
        REVIEW = "review", "Review"
        MESSAGE = "message", "Message"

    class Reason(models.TextChoices):
        # Labels match Kat's Figma.
        SPAM = "spam", "Spam or scam"
        HARASSMENT = "harassment", "Rude or harassing"
        INAPPROPRIATE = "inappropriate", "Inappropriate"
        FAKE = "fake", "Fake or misleading"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DISMISSED = "dismissed", "Dismissed"
        RESOLVED = "resolved", "Removed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )
    # Who wrote the reported content.
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_received",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    review = models.ForeignKey(
        "reviews.Review",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    message = models.ForeignKey(
        "messaging.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    # What the content said when it was reported.
    content_text = models.TextField(blank=True)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField(blank=True, max_length=MAX_DETAILS_LENGTH)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Filled in when an admin dismisses the report (#98) or removes the content (#97).
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_handled",
    )
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            # Reporting the same thing twice doesn't add a second report.
            models.UniqueConstraint(
                fields=["reporter", "review"],
                condition=Q(review__isnull=False),
                name="one_report_per_review_per_user",
            ),
            models.UniqueConstraint(
                fields=["reporter", "message"],
                condition=Q(message__isnull=False),
                name="one_report_per_message_per_user",
            ),
        ]

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    def same_content(self):
        """Every report about the same review or message, this one included."""
        target = self.review_id if self.kind == self.Kind.REVIEW else self.message_id
        if target is None:
            return Report.objects.filter(pk=self.pk)
        return Report.objects.filter(**{f"{self.kind}_id": target})

    def __str__(self):
        return f"{self.get_kind_display()} reported by {self.reporter} ({self.get_status_display()})"
