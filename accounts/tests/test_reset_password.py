"""Story #46 Reset Password: request a reset by email, choose a new password
from the emailed link, then log in with it."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
RESET_URL = reverse("password_reset")
LOGIN_URL = reverse("login")


class ResetPasswordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "kat", email="kat@example.com", password="old-pass-123!", first_name="Kat"
        )

    def request_reset(self, email="kat@example.com"):
        return self.client.post(RESET_URL, {"email": email}, follow=True)

    def reset_link(self):
        match = re.search(r"https?://[^/]+(/accounts/reset/\S+/)", mail.outbox[-1].body)
        self.assertIsNotNone(match, mail.outbox[-1].body)
        return match.group(1)

    def test_login_page_links_to_reset(self):
        response = self.client.get(LOGIN_URL)
        self.assertContains(response, "Forgot password?")
        self.assertContains(response, RESET_URL)

    def test_user_can_request_a_reset(self):
        response = self.client.get(RESET_URL)
        self.assertContains(response, "Forgot your password?")
        response = self.request_reset()
        self.assertContains(response, "Check your email")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["kat@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Reset your PawPal password")

    def test_reset_is_tied_to_the_account(self):
        self.request_reset("KAT@example.com")
        body = mail.outbox[0].body
        self.assertIn("Hi Kat", body)
        self.assertIn("(kat)", body)
        link = self.reset_link()
        response = self.client.get(link, follow=True)
        self.assertContains(response, "Choose a new password")
        self.assertContains(response, "<strong>kat</strong>")

    def test_unknown_email_gives_the_same_answer_but_sends_nothing(self):
        response = self.request_reset("nobody@example.com")
        self.assertContains(response, "Check your email")
        self.assertEqual(mail.outbox, [])

    def test_email_is_required_and_must_be_valid(self):
        self.assertContains(
            self.client.post(RESET_URL, {"email": ""}), "Enter your email."
        )
        self.assertContains(
            self.client.post(RESET_URL, {"email": "not-an-email"}),
            "Enter a valid email address.",
        )

    def test_user_can_set_a_new_password_and_log_in_with_it(self):
        self.request_reset()
        form_url = self.client.get(self.reset_link(), follow=True).redirect_chain[-1][0]
        response = self.client.post(
            form_url,
            {
                "new_password1": "brand-new-pass-456!",
                "new_password2": "brand-new-pass-456!",
            },
            follow=True,
        )
        self.assertContains(response, "Password updated")

        old = self.client.post(
            LOGIN_URL, {"username": "kat", "password": "old-pass-123!"}
        )
        self.assertContains(old, "Incorrect username or password.")
        new = self.client.post(
            LOGIN_URL, {"username": "kat", "password": "brand-new-pass-456!"}
        )
        self.assertEqual(new.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_new_passwords_must_match(self):
        self.request_reset()
        form_url = self.client.get(self.reset_link(), follow=True).redirect_chain[-1][0]
        response = self.client.post(
            form_url,
            {"new_password1": "brand-new-pass-456!", "new_password2": "different-789!"},
        )
        self.assertContains(response, "Passwords don&#x27;t match.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-pass-123!"))

    def test_link_works_only_once(self):
        self.request_reset()
        link = self.reset_link()
        form_url = self.client.get(link, follow=True).redirect_chain[-1][0]
        self.client.post(
            form_url,
            {
                "new_password1": "brand-new-pass-456!",
                "new_password2": "brand-new-pass-456!",
            },
        )
        again = self.client.get(link, follow=True)
        self.assertContains(again, "This link has expired")

    def test_bad_link_is_rejected(self):
        response = self.client.get(
            reverse("password_reset_confirm", args=["MQ", "bad-token"]), follow=True
        )
        self.assertContains(response, "This link has expired")
