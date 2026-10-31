"""Deleting an account (story #48).

The account is deactivated rather than removed, because bookings and reviews
other people can see still point to it. A deactivated user can't log in,
doesn't show up in caregiver search, and their open bookings are closed so
nobody waits on them.
"""

from django.db import transaction
from django.utils import timezone

from bookings.models import Booking


@transaction.atomic
def delete_account(user):
    now = timezone.now()
    upcoming = Booking.objects.filter(end_time__gt=now)
    open_statuses = (Booking.Status.PENDING, Booking.Status.ACCEPTED)

    # Requests this user made as a pet owner.
    upcoming.filter(owner=user, status__in=open_statuses).update(
        status=Booking.Status.CANCELLED, updated_at=now
    )

    # Requests sent to this user as a caregiver.
    profile = getattr(user, "caregiver_profile", None)
    if profile is not None:
        mine = upcoming.filter(caregiver=profile)
        mine.filter(status=Booking.Status.PENDING).update(
            status=Booking.Status.DECLINED, updated_at=now
        )
        mine.filter(status=Booking.Status.ACCEPTED).update(
            status=Booking.Status.CANCELLED, updated_at=now
        )
        profile.accepting_new_bookings = False
        profile.save(update_fields=["accepting_new_bookings"])

    # Free the email so it can be used for a new account, and lock the login.
    user.is_active = False
    user.email = ""
    user.set_unusable_password()
    user.save(update_fields=["is_active", "email", "password"])
