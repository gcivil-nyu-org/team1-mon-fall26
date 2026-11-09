"""How the admin pages describe an account: its type and its status."""

from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.restriction import is_restricted
from bookings.models import Booking
from pets.models import Pet
from reports.models import Report

PER_PAGE = 25
RECENT_BOOKINGS = 5


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

    Deleted accounts are deactivated (#48); admins can restrict an account
    (#92); new sign-ups haven't confirmed their email until they click the
    link (#197).
    """
    if not user.is_active:
        return "deleted", "Deleted"
    if is_restricted(user):
        return "restricted", "Restricted"
    profile = getattr(user, "account_profile", None)
    if profile is not None and not profile.email_verified:
        return "unverified", "Email not confirmed"
    return "active", "Active"


def account_place(user):
    """The neighborhood shown under the name: the caregiver's area, or the
    pet owner's neighborhood. Empty when we don't know it."""
    caregiver = getattr(user, "caregiver_profile", None)
    if caregiver is not None:
        return caregiver.neighborhood or caregiver.service_area
    profile = getattr(user, "account_profile", None)
    return profile.neighborhood if profile is not None else ""


def describe(user):
    """Attach what the admin pages show to a user."""
    user.type_label = account_type(user)
    user.status_key, user.status_label = account_status(user)
    user.place = account_place(user)
    return user


def all_accounts():
    """Every pet owner and caregiver account, newest first, with what the
    list needs in one query. Admin accounts aren't listed, as in the Figma."""
    return (
        get_user_model()
        .objects.filter(is_staff=False)
        .select_related("account_profile", "caregiver_profile")
        .order_by("-date_joined", "-pk")
    )


def restricted(accounts):
    """#92: the Restricted tab. Deleted accounts aren't counted as restricted."""
    return accounts.filter(is_active=True, account_profile__restricted_at__isnull=False)


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


def details(user):
    """#91: what the account page shows besides the basics.

    Pets (a deleted pet is listed but marked), the caregiver profile (its
    services are on the public profile), the latest bookings the account took part in, either as the
    pet owner or as the caregiver, and how often it has been reported.
    """
    caregiver = getattr(user, "caregiver_profile", None)
    reports = Report.objects.filter(reported_user=user).order_by("-created_at", "-pk")
    bookings = (
        Booking.objects.filter(Q(owner=user) | Q(caregiver__user=user))
        .select_related("owner", "pet", "caregiver", "service_type")
        .order_by("-start_time", "-pk")
    )
    return {
        "pets": Pet.objects.filter(owner=user)
        .select_related("pet_type")
        .order_by("deleted_at", "name"),
        "caregiver": caregiver,
        "bookings": bookings[:RECENT_BOOKINGS],
        "booking_count": bookings.count(),
        # Reports other people made about this account (#95), newest first.
        "report_count": reports.count(),
        "latest_report": reports.first(),
    }


def can_restrict(admin, account):
    """#92: admins can restrict (or reinstate) pet owners and caregivers, but
    not other admins, themselves or deleted accounts."""
    return account.is_active and not account.is_staff and account != admin
