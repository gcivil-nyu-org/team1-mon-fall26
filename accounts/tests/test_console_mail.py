"""Locally, emails are printed in the terminal. Teammates copied the verify-email
link from there and got "This link has expired": Django's console backend
printed it quoted-printable, with an "=" and a line break in the middle of the
link. Ours prints the body as written, so the copied link works."""

import io
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.console_mail import EmailBackend

User = get_user_model()
LONG_LINK = (
    "http://127.0.0.1:8000/accounts/verify-email/" + "eyJ1IjoxLCJlIjoi" * 6 + "/"
)


def printed(*messages):
    stream = io.StringIO()
    EmailBackend(stream=stream).send_messages(list(messages))
    return stream.getvalue()


class ConsoleMailTests(TestCase):
    def test_long_links_are_printed_on_one_line(self):
        message = EmailMessage(
            "Confirm your PawPal email",
            f"Hi Kat,\n\n{LONG_LINK}\n",
            "PawPal <no-reply@pawpal.app>",
            ["kat@example.com"],
        )
        # What the teammates saw: the raw email splits the link.
        self.assertNotIn(LONG_LINK, message.message().as_string())

        output = printed(message)
        self.assertIn(f"\n{LONG_LINK}\n", output)
        self.assertIn("From: PawPal <no-reply@pawpal.app>\n", output)
        self.assertIn("To: kat@example.com\n", output)
        self.assertIn("Subject: Confirm your PawPal email\n", output)
        self.assertNotIn("Content-Transfer-Encoding", output)
        self.assertTrue(output.endswith("-" * 79 + "\n"))

    def test_each_message_is_printed(self):
        output = printed(
            EmailMessage("One", "first", "a@example.com", ["b@example.com"]),
            EmailMessage("Two", "second", "a@example.com", ["c@example.com"]),
        )
        self.assertIn("Subject: One", output)
        self.assertIn("Subject: Two", output)
        self.assertEqual(output.count("-" * 79), 2)

    def test_nothing_to_send(self):
        self.assertEqual(printed(), "")

    @override_settings(
        MAILERS={"default": {"BACKEND": "accounts.console_mail.EmailBackend"}},
    )
    def test_copied_sign_up_link_confirms_the_account(self):
        stream = io.StringIO()
        with mock.patch("sys.stdout", stream):
            self.client.post(
                reverse("signup"),
                {
                    "username": "madi",
                    "first_name": "Madi",
                    "last_name": "P",
                    "email": "madi@example.com",
                    "password1": "a-new-pass-123!",
                    "password2": "a-new-pass-123!",
                    "account_type": "pet_owner",
                },
            )
        path = re.search(
            r"https?://[^/\s]+(/accounts/verify-email/\S+/)", stream.getvalue()
        )
        self.assertIsNotNone(path, stream.getvalue())
        self.client.get(path.group(1))
        user = User.objects.get(username="madi")
        self.assertTrue(user.account_profile.email_verified)
