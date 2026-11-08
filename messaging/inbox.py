"""Building the inbox: which conversations a user has, what's unread, and how
each one is shown (the other person, the booking status, the preview line)."""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.db.models import Case, Exists, F, OuterRef, Q, Subquery, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from bookings.models import Booking
from bookings.views import owner_name
from caregivers.templatetags.caregiver_tags import avatar_theme, initials

from .models import Conversation, Message

# Treat "never opened" as opened long ago, so every message counts as new.
NEVER = datetime(2000, 1, 1, tzinfo=dt_timezone.utc)
# Avatar colors for pet owners, picked by account id.
OWNER_THEMES = ("yellow", "blue", "mint", "pink", "peach")


def conversations_for(user):
    """Every conversation the user takes part in, as owner or as caregiver."""
    return Conversation.objects.filter(
        Q(owner=user) | Q(caregiver__user=user)
    ).select_related(
        "owner",
        "owner__account_profile",
        "caregiver",
        "caregiver__user",
        "booking__pet",
        "booking__service_type",
    )


def with_unread(conversations, user):
    """Mark each conversation `unread` if the other person wrote since the user last looked."""
    read_at = Coalesce(
        Case(
            When(owner=user, then=F("owner_read_at")),
            default=F("caregiver_read_at"),
        ),
        NEVER,
    )
    newer = (
        Message.objects.visible()
        .filter(conversation=OuterRef("pk"), created_at__gt=OuterRef("my_read_at"))
        .exclude(sender=user)
    )
    return conversations.annotate(my_read_at=read_at).annotate(unread=Exists(newer))


def unread_count(user):
    """How many conversations have messages the user hasn't seen (the nav badge)."""
    return with_unread(conversations_for(user), user).filter(unread=True).count()


def inbox(user):
    """The user's conversations that have messages, newest first, ready to show."""
    latest = (
        Message.objects.visible()
        .filter(conversation=OuterRef("pk"))
        .order_by("-created_at", "-pk")
    )
    conversations = (
        with_unread(conversations_for(user), user)
        .filter(last_message_at__isnull=False)
        .annotate(
            last_body=Subquery(latest.values("body")[:1]),
            last_sender_id=Subquery(latest.values("sender_id")[:1]),
        )
        .order_by("-last_message_at", "-pk")
    )
    return [describe(c, user) for c in conversations]


def describe(conversation, user):
    """Attach what the page shows about a conversation for this viewer."""
    conversation.other = counterpart(conversation, user)
    conversation.state = booking_state(conversation.booking)
    conversation.viewer_is_owner = conversation.is_owner(user)
    body = getattr(conversation, "last_body", None)
    if body is not None:
        mine = conversation.last_sender_id == user.pk
        conversation.preview = f"You: {body}" if mine else body
    return conversation


def counterpart(conversation, user):
    """The other person in the conversation, as the header and inbox show them."""
    if conversation.is_owner(user):
        caregiver = conversation.caregiver
        place = caregiver.neighborhood or caregiver.service_area
        return {
            "name": caregiver.name,
            "first_name": caregiver.name.split()[0] if caregiver.name else "",
            "role": "Caregiver",
            "place": place,
            "initials": initials(caregiver.name),
            "theme": avatar_theme(caregiver),
        }
    owner = conversation.owner
    full = owner.get_full_name() or owner.username
    profile = getattr(owner, "account_profile", None)
    return {
        "name": owner_name(owner),
        "first_name": owner.first_name.strip() or owner.username,
        "role": "Pet owner",
        "place": profile.neighborhood if profile else "",
        "initials": initials(full),
        "theme": OWNER_THEMES[owner.pk % len(OWNER_THEMES)],
    }


def booking_state(booking, now=None):
    """The status pill for a booking: its status, or "In progress" while care is happening."""
    if booking is None:
        return None
    now = now or timezone.now()
    if (
        booking.status == Booking.Status.ACCEPTED
        and booking.start_time <= now < booking.end_time
    ):
        return {"key": "in-progress", "label": "In progress"}
    return {"key": booking.status, "label": booking.get_status_display()}


def day_label(moment, today=None):
    """ "Today", "Yesterday", "Sat, Oct 3" (with the year if it isn't this year)."""
    local = timezone.localtime(moment)
    today = today or timezone.localdate()
    if local.date() == today:
        return "Today"
    if local.date() == today - timedelta(days=1):
        return "Yesterday"
    if local.year == today.year:
        return local.strftime("%a, %b ") + str(local.day)
    return local.strftime("%a, %b ") + f"{local.day}, {local.year}"


def by_day(messages):
    """Messages grouped under a label for each day they were sent."""
    groups = []
    for message in messages:
        label = day_label(message.created_at)
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "messages": []})
        groups[-1]["messages"].append(message)
    return groups
