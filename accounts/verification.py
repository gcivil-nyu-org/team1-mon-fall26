"""Email verification for new accounts: the signed link we email and checking it.

The link carries the user's id and email, signed with SECRET_KEY, so it can't be
forged and stops working if the email changes or the account is deleted.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

SALT = "accounts.verify-email"


def needs_verification(user):
    profile = getattr(user, "account_profile", None)
    return profile is not None and not profile.email_verified


def mark_verified(user):
    profile = getattr(user, "account_profile", None)
    if profile is not None and not profile.email_verified:
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])


def make_token(user):
    return signing.dumps({"u": user.pk, "e": user.email}, salt=SALT)


def user_from_token(token):
    """The account the link was made for, or None if it's bad, expired or out of date."""
    try:
        data = signing.loads(
            token, salt=SALT, max_age=settings.EMAIL_VERIFICATION_TIMEOUT
        )
    except signing.BadSignature:  # includes SignatureExpired
        return None
    user = get_user_model().objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or not user.email or user.email != data.get("e"):
        return None
    return user


def send_verification_email(request, user):
    link = request.build_absolute_uri(reverse("verify_email", args=[make_token(user)]))
    context = {"user": user, "link": link}
    subject = render_to_string("accounts/emails/verify_email_subject.txt", context)
    body = render_to_string("accounts/emails/verify_email.txt", context)
    send_mail(subject.strip(), body, None, [user.email])
