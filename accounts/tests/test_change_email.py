"""#47 Update Personal Information: a pet owner can change their email on Edit
your profile. The new email only replaces the old one once they click the
link we send to it, and the old address is told about the change."""

import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AccountProfile
from accounts.verification import CHANGE_SALT, make_change_token, make_token

User = get_user_model()
EDIT_URL = reverse("edit_profile")
PROFILE_URL = reverse("my_profile")


def confirm_url(token):
    return reverse("confirm_email_change", args=[token])


def link_in(message):
    match = re.search(r"https?://[^/\s]+(/accounts/profile/email/\S+/)", message.body)
    return match.group(1)


class ChangeEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "kat", email="kat@example.com", first_name="Kat", last_name="W"
        )
        AccountProfile.objects.create(
            user=cls.owner,
            address="215 6th Ave, Brooklyn",
            neighborhood="Park Slope, Brooklyn",
        )
        User.objects.create_user("chloe", email="chloe@example.com")

    def setUp(self):
        self.client.force_login(self.owner)

    def save(self, email):
        return self.client.post(
            EDIT_URL,
            {
                "first_name": "Kat",
                "last_name": "W",
                "email": email,
                "address": "215 6th Ave, Brooklyn",
            },
            follow=True,
        )

    def refresh(self):
        self.owner.refresh_from_db()
        return self.owner.email

    def test_new_email_waits_for_the_link(self):
        response = self.save(" Kat.New@Example.com ")
        self.assertRedirects(response, PROFILE_URL)
        self.assertContains(
            response,
            "We sent a link to kat.new@example.com. Your email changes once you "
            "click it.",
        )
        self.assertContains(response, "Your profile is saved.")
        self.assertEqual(self.refresh(), "kat@example.com")

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["kat.new@example.com"])
        self.assertEqual(sent.subject, "Confirm your new PawPal email")
        self.assertIn("Hi Kat", sent.body)
        self.assertIn("we keep using your old email", sent.body)

    def test_clicking_the_link_changes_the_email_and_tells_the_old_one(self):
        self.save("kat.new@example.com")
        link = link_in(mail.outbox[0])
        response = self.client.get(link, follow=True)
        self.assertRedirects(response, PROFILE_URL)
        self.assertContains(response, "Your email is now kat.new@example.com.")
        self.assertContains(response, "kat.new@example.com</dd>")
        self.assertEqual(self.refresh(), "kat.new@example.com")

        notice = mail.outbox[1]
        self.assertEqual(notice.to, ["kat@example.com"])
        self.assertEqual(notice.subject, "Your PawPal email was changed")
        self.assertIn("from kat@example.com to kat.new@example.com", notice.body)

        # Clicking it again just says so.
        response = self.client.get(link, follow=True)
        self.assertContains(response, "Your email is already kat.new@example.com.")
        self.assertEqual(len(mail.outbox), 2)

    def test_link_works_when_logged_out(self):
        self.save("kat.new@example.com")
        link = link_in(mail.outbox[0])
        self.client.logout()
        response = self.client.get(link)
        self.assertRedirects(response, PROFILE_URL, fetch_redirect_response=False)
        self.assertEqual(self.refresh(), "kat.new@example.com")

    def test_confirming_also_confirms_an_unverified_account(self):
        self.owner.account_profile.email_verified = False
        self.owner.account_profile.save()
        self.client.get(confirm_url(make_change_token(self.owner, "k2@example.com")))
        self.owner.account_profile.refresh_from_db()
        self.assertTrue(self.owner.account_profile.email_verified)

    def test_same_email_sends_nothing(self):
        response = self.save("KAT@example.com")
        self.assertNotContains(response, "We sent a link")
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.refresh(), "kat@example.com")

    def test_email_of_another_account_is_refused(self):
        response = self.save("Chloe@example.com")
        self.assertContains(response, "This email already has an account.")
        self.assertEqual(mail.outbox, [])

    def test_invalid_email_is_refused(self):
        response = self.save("not-an-email")
        self.assertContains(response, "Enter a valid email address.")

    def assertExpired(self, token):
        response = self.client.get(confirm_url(token))
        self.assertTemplateUsed(response, "accounts/email_change_invalid.html")
        self.assertContains(response, "This link has expired")
        self.assertContains(response, f'href="{EDIT_URL}"')
        self.assertEqual(self.refresh(), "kat@example.com")

    def test_bad_link(self):
        self.assertExpired("not-a-token")

    def test_old_link(self):
        token = make_change_token(self.owner, "kat.new@example.com")
        with override_settings(EMAIL_VERIFICATION_TIMEOUT=-1):
            self.assertExpired(token)

    def test_link_from_before_the_email_changed_again(self):
        first = make_change_token(self.owner, "one@example.com")
        self.client.get(confirm_url(make_change_token(self.owner, "two@example.com")))
        self.assertEqual(self.refresh(), "two@example.com")
        response = self.client.get(confirm_url(first))
        self.assertContains(response, "This link has expired")
        self.assertEqual(self.refresh(), "two@example.com")

    def test_email_taken_since_the_link_was_sent(self):
        token = make_change_token(self.owner, "taken@example.com")
        User.objects.create_user("sam", email="taken@example.com")
        self.assertExpired(token)

    def test_deleted_account(self):
        token = make_change_token(self.owner, "kat.new@example.com")
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        response = self.client.get(confirm_url(token))
        self.assertContains(response, "This link has expired")

    def test_link_without_a_new_email(self):
        token = signing.dumps(
            {"u": self.owner.pk, "old": "kat@example.com"}, salt=CHANGE_SALT
        )
        self.assertExpired(token)

    def test_sign_up_link_cant_change_the_email(self):
        self.assertExpired(make_token(self.owner))

    def test_no_notice_when_there_was_no_old_email(self):
        User.objects.filter(pk=self.owner.pk).update(email="")
        self.owner.refresh_from_db()
        self.client.get(confirm_url(make_change_token(self.owner, "k@example.com")))
        self.assertEqual(self.refresh(), "k@example.com")
        self.assertEqual(mail.outbox, [])

    @mock.patch("accounts.forms.geocode", return_value=None)
    def test_nothing_is_sent_when_the_form_has_errors(self, geocode):
        response = self.client.post(
            EDIT_URL,
            {
                "first_name": "Kat",
                "last_name": "W",
                "email": "kat.new@example.com",
                "address": "1 Main St, Boston",
            },
        )
        self.assertContains(response, "We couldn&#x27;t find this address")
        self.assertEqual(mail.outbox, [])
