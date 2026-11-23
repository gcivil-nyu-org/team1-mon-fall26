"""Which side of PawPal an account is on.

Pet owners request care and post care opportunities; caregivers answer them.
Navigation only shows each role its own pages, and these checks make the
pages themselves refuse the other role when someone opens them by URL.
"""

from django.contrib import messages
from django.shortcuts import redirect

from .models import AccountProfile


def is_caregiver(user):
    """True for an account with a caregiver profile or signed up as a caregiver."""
    if getattr(user, "caregiver_profile", None) is not None:
        return True
    profile = getattr(user, "account_profile", None)
    return profile is not None and profile.role == AccountProfile.Role.CAREGIVER


def owners_only(request, message="Use a pet owner account for this page."):
    """A redirect for caregivers opening a pet owner page, else None."""
    if is_caregiver(request.user):
        messages.info(request, message)
        return redirect("bookings:caregiver_requests")
    return None
