"""Email verification: a new account works only after its owner clicks the link
we email them. Resetting the password by email also confirms the email."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AccountProfile
from accounts.verification import make_token

User = get_user_model()
SIGNUP_URL = reverse("signup")
LOGIN_URL = reverse("login")
SENT_URL = reverse("verify_email_sent")
RESEND_URL = reverse("resend_verification")

SIGNUP = {
    "username": "kat",
    "first_name": "Kat",
    "last_name": "W",
    "email": "Kat@Example.com",
    "password1": "a-new-pass-123!",
    "password2": "a-new-pass-123!",
    "account_type": "pet_owner",
}


def link_in(message):
    match = re.search(r"https?://[^/\s]+(/accounts/verify-email/\S+/)", message.body)
    return match.group(1)


class SignUpVerificationTests(TestCase):
    def sign_up(self, **changes):
        return self.client.post(SIGNUP_URL, {**SIGNUP, **changes}, follow=True)

    def log_in(self, password="a-new-pass-123!"):
        return self.client.post(LOGIN_URL, {"username": "kat", "password": password})

    def test_sign_up_sends_a_link_instead_of_logging_in(self):
        response = self.sign_up()
        self.assertRedirects(response, SENT_URL)
        self.assertContains(response, "Confirm your email")
        self.assertContains(response, "<strong>kat@example.com</strong>")
        self.assertNotIn("_auth_user_id", self.client.session)

        user = User.objects.get(username="kat")
        self.assertTrue(user.is_active)
        self.assertFalse(user.account_profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["kat@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Confirm your PawPal email")
        self.assertIn("Hi Kat", mail.outbox[0].body)

    def test_cannot_log_in_before_confirming(self):
        self.sign_up()
        response = self.log_in()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm your email before you log in.")
        self.assertContains(response, "kat@example.com")
        self.assertContains(response, f'href="{SENT_URL}"')
        self.assertNotContains(response, "Incorrect username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_still_says_incorrect(self):
        self.sign_up()
        response = self.log_in("wrong-password")
        self.assertContains(response, "Incorrect username or password.")
        self.assertNotContains(response, "Confirm your email before you log in.")

    def test_link_confirms_and_logs_in(self):
        self.sign_up()
        response = self.client.get(link_in(mail.outbox[0]), follow=True)
        self.assertRedirects(response, reverse("signup_success"))
        self.assertContains(response, "Welcome, Kat!")
        user = User.objects.get(username="kat")
        self.assertTrue(user.account_profile.email_verified)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        self.client.logout()
        self.assertEqual(self.log_in().status_code, 302)

    def test_using_the_link_again_goes_to_log_in(self):
        self.sign_up()
        link = link_in(mail.outbox[0])
        self.client.get(link)
        self.client.logout()
        response = self.client.get(link, follow=True)
        self.assertRedirects(response, LOGIN_URL)
        self.assertContains(response, "Your email is already confirmed.")

    def test_bad_link_is_rejected(self):
        self.sign_up()
        link = link_in(mail.outbox[0])
        response = self.client.get(link[:-3] + "xx/")
        self.assertContains(response, "This link has expired")
        self.assertFalse(
            User.objects.get(username="kat").account_profile.email_verified
        )

    @override_settings(EMAIL_VERIFICATION_TIMEOUT=-1)
    def test_expired_link_is_rejected(self):
        self.sign_up()
        response = self.client.get(link_in(mail.outbox[0]))
        self.assertContains(response, "This link has expired")
        self.assertContains(response, f'action="{RESEND_URL}"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_link_stops_working_if_the_email_changes(self):
        self.sign_up()
        link = link_in(mail.outbox[0])
        User.objects.filter(username="kat").update(email="other@example.com")
        self.assertContains(self.client.get(link), "This link has expired")

    def test_link_for_a_deleted_account_does_not_work(self):
        self.sign_up()
        link = link_in(mail.outbox[0])
        User.objects.filter(username="kat").update(is_active=False)
        self.assertContains(self.client.get(link), "This link has expired")


class ResendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "kat", email="kat@example.com", password="a-new-pass-123!"
        )
        AccountProfile.objects.create(user=self.user, email_verified=False)

    def resend(self, email):
        return self.client.post(RESEND_URL, {"email": email}, follow=True)

    def test_sends_a_new_link(self):
        response = self.resend("KAT@example.com")
        self.assertRedirects(response, SENT_URL)
        self.assertContains(response, "We sent you a new link.")
        self.assertEqual(mail.outbox[0].to, ["kat@example.com"])
        self.client.get(link_in(mail.outbox[0]))
        self.user.account_profile.refresh_from_db()
        self.assertTrue(self.user.account_profile.email_verified)

    def test_same_answer_but_no_email_for_unknown_or_confirmed_accounts(self):
        self.assertContains(
            self.resend("nobody@example.com"), "We sent you a new link."
        )
        AccountProfile.objects.filter(user=self.user).update(email_verified=True)
        self.assertContains(self.resend("kat@example.com"), "We sent you a new link.")
        self.assertEqual(mail.outbox, [])

    def test_email_is_required_and_must_be_valid(self):
        self.assertContains(
            self.client.post(RESEND_URL, {"email": ""}), "Enter your email."
        )
        self.assertContains(
            self.client.post(RESEND_URL, {"email": "nope"}),
            "Enter a valid email address.",
        )

    def test_resend_is_post_only(self):
        self.assertEqual(self.client.get(RESEND_URL).status_code, 405)

    def test_sent_page_without_a_sign_up(self):
        response = self.client.get(SENT_URL)
        self.assertContains(response, "We sent a link to the email on your account.")

    def test_reset_password_also_confirms_the_email(self):
        self.client.post(reverse("password_reset"), {"email": "kat@example.com"})
        link = re.search(r"https?://[^/]+(/accounts/reset/\S+/)", mail.outbox[0].body)
        form_url = self.client.get(link.group(1), follow=True).redirect_chain[-1][0]
        self.client.post(
            form_url,
            {"new_password1": "brand-new-456!x", "new_password2": "brand-new-456!x"},
        )
        self.user.account_profile.refresh_from_db()
        self.assertTrue(self.user.account_profile.email_verified)
        response = self.client.post(
            LOGIN_URL, {"username": "kat", "password": "brand-new-456!x"}
        )
        self.assertEqual(response.status_code, 302)


class ExistingAccountTests(TestCase):
    def test_accounts_made_before_verification_can_still_log_in(self):
        user = User.objects.create_user("old", password="a-new-pass-123!")
        profile = AccountProfile.objects.create(user=user)
        self.assertTrue(profile.email_verified)
        response = self.client.post(
            LOGIN_URL, {"username": "old", "password": "a-new-pass-123!"}
        )
        self.assertEqual(response.status_code, 302)

    def test_accounts_without_a_profile_can_log_in(self):
        User.objects.create_superuser("admin", password="a-new-pass-123!")
        response = self.client.post(
            LOGIN_URL, {"username": "admin", "password": "a-new-pass-123!"}
        )
        self.assertEqual(response.status_code, 302)

    def test_token_for_a_missing_account_does_not_work(self):
        user = User.objects.create_user("gone", email="gone@example.com")
        token = make_token(user)
        user.delete()
        response = self.client.get(reverse("verify_email", args=[token]))
        self.assertContains(response, "This link has expired")
