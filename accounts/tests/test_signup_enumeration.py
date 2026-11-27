"""Signing up with an email that already has an account looks the same as a
new sign-up; the owner gets an email about it instead (#317)."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .test_verify_email import SENT_URL, SIGNUP, SIGNUP_URL

User = get_user_model()


class ExistingEmailTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "katw", email="kat@example.com", password="pw-12345!", first_name="Kat"
        )

    def test_page_does_not_say_the_email_is_taken(self):
        response = self.client.post(SIGNUP_URL, {**SIGNUP, "username": "newkat"})
        self.assertRedirects(response, SENT_URL)
        response = self.client.get(SENT_URL)
        self.assertNotContains(response, "already has an account")
        self.assertFalse(User.objects.filter(username="newkat").exists())

    def test_owner_is_emailed_instead(self):
        self.client.post(SIGNUP_URL, {**SIGNUP, "username": "newkat"})
        (message,) = mail.outbox
        self.assertEqual(message.to, ["kat@example.com"])
        self.assertIn("already has an account (katw)", message.body)
        self.assertIn(reverse("password_reset"), message.body)

    def test_new_email_signs_up_as_before(self):
        response = self.client.post(
            SIGNUP_URL, {**SIGNUP, "username": "sam", "email": "sam@example.com"}
        )
        self.assertRedirects(response, SENT_URL)
        self.assertTrue(User.objects.filter(username="sam").exists())
        self.assertIn("Confirm your email", mail.outbox[0].body)

    def test_other_errors_still_show_without_mentioning_the_email(self):
        response = self.client.post(
            SIGNUP_URL, {**SIGNUP, "username": "newkat", "password2": "different"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "already has an account")
        self.assertEqual(mail.outbox, [])
