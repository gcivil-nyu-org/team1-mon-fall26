"""Messages between pet owners and caregivers (stories: Message before a
Service, View Message History, Inbox + Care Updates)."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

# Longest message someone can send.
MAX_MESSAGE_LENGTH = 2000


class Conversation(models.Model):
    """A chat between a pet owner and a caregiver.

    A conversation either belongs to one booking (shown with the booking card),
    or has no booking: the owner's questions before requesting care. Each owner
    and caregiver pair has at most one conversation without a booking.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_conversations",
    )
    caregiver = models.ForeignKey(
        "caregivers.CaregiverProfile",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="conversation",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # When the newest message was sent; empty until the first message.
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # When each side last opened the conversation, for unread markers.
    owner_read_at = models.DateTimeField(null=True, blank=True)
    caregiver_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "caregiver"],
                condition=Q(booking__isnull=True),
                name="one_general_conversation_per_pair",
            )
        ]

    def __str__(self):
        about = f"booking #{self.booking_id}" if self.booking_id else "no booking"
        return f"{self.owner} and {self.caregiver} ({about})"

    def get_absolute_url(self):
        return reverse("messaging:conversation", args=[self.pk])

    def is_owner(self, user):
        return self.owner_id == user.pk

    def other_can_receive(self, user):
        """False once the other person's account has been deleted (deactivated)."""
        other = self.caregiver.user if self.is_owner(user) else self.owner
        return other is None or other.is_active

    def mark_read(self, user, when=None):
        """Remember that `user` has seen everything up to now."""
        field = "owner_read_at" if self.is_owner(user) else "caregiver_read_at"
        when = when or timezone.now()
        Conversation.objects.filter(pk=self.pk).update(**{field: when})
        setattr(self, field, when)


class MessageQuerySet(models.QuerySet):
    def visible(self):
        """Messages users can see: not removed by an admin (#97)."""
        return self.filter(removed_at__isnull=True)


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    body = models.TextField(max_length=MAX_MESSAGE_LENGTH)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    # Set when an admin removes the message after a report (#97). Users stop
    # seeing it; admins still see it, crossed out, on the report.
    removed_at = models.DateTimeField(null=True, blank=True)

    objects = MessageQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"
