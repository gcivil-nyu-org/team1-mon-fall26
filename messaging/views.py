"""The Messages page: inbox, conversation history, sending messages, and
starting a conversation before a service or about a booking."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from bookings.models import Booking
from caregivers.models import CaregiverProfile

from .inbox import by_day, conversations_for, counterpart, describe, inbox
from .models import MAX_MESSAGE_LENGTH, Conversation, Message


def closed_account_notice(first_name):
    return f"{first_name}’s account has been deleted, so they can’t receive messages."


@login_required
def inbox_view(request):
    """All conversations. None is opened (or marked read) until the user picks one."""
    Booking.update_overdue()
    return render(
        request, "messaging/inbox.html", {"conversations": inbox(request.user)}
    )


@login_required
def conversation_view(request, pk):
    """One conversation's full history, next to the inbox."""
    Booking.update_overdue()
    selected = get_object_or_404(conversations_for(request.user), pk=pk)
    conversations = inbox(request.user)
    match = next((c for c in conversations if c.pk == selected.pk), None)
    if match is None:
        # A new conversation with no messages yet: show it at the top.
        match = describe(selected, request.user)
        conversations.insert(0, match)
    return _show(request, conversations, match)


def _show(request, conversations, selected):
    history = list(selected.messages.visible().select_related("sender"))
    # Opening a conversation is what counts as reading it.
    selected.mark_read(request.user)
    selected.unread = False
    other = selected.other
    return render(
        request,
        "messaging/inbox.html",
        {
            "conversations": conversations,
            "selected": selected,
            "days": by_day(history),
            "latest_id": history[-1].pk if history else 0,
            "max_length": MAX_MESSAGE_LENGTH,
            "can_reply": selected.other_can_receive(request.user),
            "can_request_care": (
                selected.viewer_is_owner
                and selected.booking_id is None
                and selected.caregiver.accepting_new_bookings
            ),
            "placeholder": f"Message {other['first_name']}…",
        },
    )


@login_required
@require_POST
def send_message(request, pk):
    conversation = get_object_or_404(conversations_for(request.user), pk=pk)
    body = request.POST.get("body", "").strip()
    if not conversation.other_can_receive(request.user):
        name = counterpart(conversation, request.user)["first_name"]
        messages.error(request, closed_account_notice(name))
    elif not body:
        messages.error(request, "Write a message before sending.")
    elif len(body) > MAX_MESSAGE_LENGTH:
        messages.error(
            request, f"Messages can be up to {MAX_MESSAGE_LENGTH:,} characters."
        )
    else:
        now = timezone.now()
        Message.objects.create(
            conversation=conversation, sender=request.user, body=body, created_at=now
        )
        Conversation.objects.filter(pk=conversation.pk).update(last_message_at=now)
        conversation.mark_read(request.user, now)
    return redirect(f"{conversation.get_absolute_url()}#latest")


@login_required
def latest_message(request, pk):
    """The newest message id, so an open conversation can refresh when one arrives."""
    conversation = get_object_or_404(conversations_for(request.user), pk=pk)
    newest = conversation.messages.visible().order_by("-created_at", "-pk").first()
    return JsonResponse({"latest_id": newest.pk if newest else 0})


@login_required
def message_caregiver(request, caregiver_pk):
    """An owner asks a caregiver questions before requesting care."""
    # Deleted (inactive) caregiver accounts can't be messaged.
    caregiver = get_object_or_404(
        CaregiverProfile, pk=caregiver_pk, user__isnull=False, user__is_active=True
    )
    if caregiver.user_id == request.user.pk or getattr(
        request.user, "caregiver_profile", None
    ):
        messages.info(
            request,
            "Caregiver accounts reply to pet owners from Messages "
            "and their care requests.",
        )
        return redirect("caregiver", pk=caregiver.pk)
    conversation, _ = Conversation.objects.get_or_create(
        owner=request.user, caregiver=caregiver, booking=None
    )
    return redirect(conversation)


@login_required
def message_about_booking(request, booking_pk):
    """The owner or the caregiver of a booking opens its conversation."""
    booking = get_object_or_404(
        Booking.objects.filter(Q(owner=request.user) | Q(caregiver__user=request.user)),
        pk=booking_pk,
    )
    conversation, _ = Conversation.objects.get_or_create(
        booking=booking,
        defaults={"owner": booking.owner, "caregiver": booking.caregiver},
    )
    return redirect(conversation)
