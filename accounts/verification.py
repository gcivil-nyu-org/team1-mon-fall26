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


# Changing the email (#47). The new email only replaces the old one once the
# link we send to the new address is clicked, so nobody can put an email they
# don't own on their account. The link carries the old email too, so it stops
# working once the email has changed (or changed again).

CHANGE_SALT = "accounts.change-email"


def make_change_token(user, new_email):
    return signing.dumps(
        {"u": user.pk, "old": user.email, "new": new_email}, salt=CHANGE_SALT
    )


def email_change_from_token(token):
    """(user, old email, new email) for a good link, or None if it's bad or expired."""
    try:
        data = signing.loads(
            token, salt=CHANGE_SALT, max_age=settings.EMAIL_VERIFICATION_TIMEOUT
        )
    except signing.BadSignature:  # includes SignatureExpired
        return None
    user = get_user_model().objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or not data.get("new"):
        return None
    return user, data.get("old"), data["new"]


def email_taken(email, user):
    """Another account already uses this email."""
    return (
        get_user_model()
        .objects.filter(email__iexact=email)
        .exclude(pk=user.pk)
        .exists()
    )


def send_change_email(request, user, new_email):
    link = request.build_absolute_uri(
        reverse("confirm_email_change", args=[make_change_token(user, new_email)])
    )
    context = {"user": user, "link": link, "new_email": new_email}
    subject = render_to_string("accounts/emails/change_email_subject.txt", context)
    body = render_to_string("accounts/emails/change_email.txt", context)
    send_mail(subject.strip(), body, None, [new_email])


def send_email_changed_notice(user, old_email):
    """Tell the old address, in case someone else changed it."""
    context = {"user": user, "old_email": old_email}
    subject = render_to_string("accounts/emails/email_changed_subject.txt", context)
    body = render_to_string("accounts/emails/email_changed.txt", context)
    send_mail(subject.strip(), body, None, [old_email])
