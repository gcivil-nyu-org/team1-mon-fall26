"""#92: admins restrict an account while they look into a problem, and
reinstate it afterwards. A restricted account can't log in, is logged out of
any open session, and caregivers stop showing in search."""

from django.utils import timezone

from .models import AccountProfile

RESTRICTED_MESSAGE = (
    "This account is restricted. Contact the PawPal team if you think this "
    "is a mistake."
)


def is_restricted(user):
    profile = getattr(user, "account_profile", None)
    return profile is not None and profile.restricted_at is not None


def restrict(user, reason=""):
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.restricted_at = timezone.now()
    profile.restriction_reason = reason.strip()
    profile.save(update_fields=["restricted_at", "restriction_reason"])


def reinstate(user):
    AccountProfile.objects.filter(user=user).update(
        restricted_at=None, restriction_reason=""
    )


# #103: only forum posting is restricted. They can still read the forum and
# use the rest of PawPal.
def is_forum_restricted(user):
    profile = getattr(user, "account_profile", None)
    return profile is not None and profile.forum_restricted_at is not None


def restrict_forum(user):
    profile, _ = AccountProfile.objects.get_or_create(user=user)
    profile.forum_restricted_at = timezone.now()
    profile.save(update_fields=["forum_restricted_at"])


def restore_forum(user):
    AccountProfile.objects.filter(user=user).update(forum_restricted_at=None)
