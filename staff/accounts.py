"""How the admin pages describe an account: its type and its status."""

from django.contrib.auth import get_user_model
from django.db.models import Q

PER_PAGE = 25


def account_type(user):
    """Admin, Caregiver or Pet owner (the same rule the site header uses)."""
    if user.is_staff:
        return "Admin"
    profile = getattr(user, "account_profile", None)
    if hasattr(user, "caregiver_profile") or (profile and profile.role == "caregiver"):
        return "Caregiver"
    return "Pet owner"


def account_status(user):
    """(key, label) for the status pill.

    Deleted accounts are deactivated (#48); new sign-ups haven't confirmed
    their email yet until they click the link (#197).
    """
    if not user.is_active:
        return "deleted", "Deleted"
    profile = getattr(user, "account_profile", None)
    if profile is not None and not profile.email_verified:
        return "unverified", "Email not confirmed"
    return "active", "Active"


def describe(user):
    """Attach what the admin pages show to a user."""
    user.type_label = account_type(user)
    user.status_key, user.status_label = account_status(user)
    return user


def all_accounts():
    """Every account, newest first, with what the list needs in one query."""
    return (
        get_user_model()
        .objects.select_related("account_profile", "caregiver_profile")
        .order_by("-date_joined", "-pk")
    )


def search(accounts, query):
    """#90: accounts whose name, username or email contains every word typed.

    Case doesn't matter, so "kat w" finds Kat Wongsri.
    """
    for word in query.split():
        accounts = accounts.filter(
            Q(username__icontains=word)
            | Q(email__icontains=word)
            | Q(first_name__icontains=word)
            | Q(last_name__icontains=word)
        )
    return accounts
