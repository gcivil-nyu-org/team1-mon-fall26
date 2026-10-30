"""Story #48 Delete Account: the user confirms with their password, the account
is deactivated, and they can't log in with it any more."""

from datetime import timedelta

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from bookings.tests.test_bookings import BookingTestData
from caregivers.search import searchable_caregivers

User = get_user_model()
DELETE_URL = reverse("delete_account")
LOGIN_URL = reverse("login")


def past(**fields):
    start = timezone.now() - timedelta(days=2)
    return {"start_time": start, "end_time": start + timedelta(hours=1), **fields}


class DeleteAccountTests(BookingTestData):
    def setUp(self):
        self.owner.email = "owner@example.com"
        self.owner.save()
        self.sitter = User.objects.create_user("sitter", password="pw-12345!")
        self.caregiver.user = self.sitter
        self.caregiver.save()

    def delete(self, user, password="pw-12345!"):
        self.client.force_login(user)
        return self.client.post(DELETE_URL, {"password": password}, follow=True)

    def test_menu_links_to_delete_account(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("pets:list"))
        self.assertContains(response, f'href="{DELETE_URL}"')

    def test_signed_out_visitors_go_to_login(self):
        response = self.client.get(DELETE_URL)
        self.assertRedirects(response, f"{LOGIN_URL}?next={DELETE_URL}")

    def test_asks_for_confirmation_first(self):
        self.client.force_login(self.owner)
        response = self.client.get(DELETE_URL)
        self.assertContains(response, "Delete your account?")
        self.assertContains(response, "Enter your password to confirm")
        self.assertContains(response, "Keep my account")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_wrong_or_missing_password_keeps_the_account(self):
        for password in ("wrong-password", ""):
            response = self.delete(self.owner, password)
            self.assertEqual(response.status_code, 200)
            self.owner.refresh_from_db()
            self.assertTrue(self.owner.is_active)
        self.assertContains(response, "Enter your password to confirm.")
        wrong = self.delete(self.owner, "wrong-password")
        self.assertContains(wrong, "That password isn&#x27;t right.")

    def test_confirmed_deletion_deactivates_and_logs_out(self):
        response = self.delete(self.owner)
        self.assertRedirects(response, LOGIN_URL)
        self.assertContains(response, "Your PawPal account has been deleted.")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertEqual(self.owner.email, "")
        self.assertFalse(self.owner.has_usable_password())

    def test_deleted_account_cannot_log_in(self):
        self.delete(self.owner)
        response = self.client.post(
            LOGIN_URL, {"username": "owner", "password": "pw-12345!"}
        )
        self.assertContains(response, "Incorrect username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_email_can_be_used_for_a_new_account(self):
        self.delete(self.owner)
        response = self.client.post(
            reverse("signup"),
            {
                "username": "owner2",
                "first_name": "Kat",
                "last_name": "W",
                "email": "owner@example.com",
                "password1": "a-new-pass-123!",
                "password2": "a-new-pass-123!",
                "account_type": "pet_owner",
            },
        )
        self.assertRedirects(response, reverse("signup_success"))

    def test_deleted_account_gets_no_reset_email(self):
        # #46 + #48: the email was cleared and the account is inactive.
        self.delete(self.owner)
        response = self.client.post(
            reverse("password_reset"), {"email": "owner@example.com"}, follow=True
        )
        self.assertContains(response, "Check your email")
        self.assertEqual(mail.outbox, [])

    def test_reset_link_sent_before_deletion_stops_working(self):
        self.client.post(reverse("password_reset"), {"email": "owner@example.com"})
        link = re.search(r"https?://[^/]+(/accounts/reset/\S+/)", mail.outbox[0].body)
        self.delete(self.owner)
        self.client.logout()
        response = self.client.get(link.group(1), follow=True)
        self.assertContains(response, "This link has expired")

    def test_owners_open_bookings_are_cancelled(self):
        pending = self.make_booking()
        accepted = self.make_booking(status=Booking.Status.ACCEPTED)
        done = self.make_booking(**past(status=Booking.Status.COMPLETED))
        self.delete(self.owner)
        for booking, status in (
            (pending, Booking.Status.CANCELLED),
            (accepted, Booking.Status.CANCELLED),
            (done, Booking.Status.COMPLETED),
        ):
            booking.refresh_from_db()
            self.assertEqual(booking.status, status)

    def test_caregiver_is_hidden_and_their_requests_closed(self):
        pending = self.make_booking()
        accepted = self.make_booking(status=Booking.Status.ACCEPTED)
        self.assertIn(self.caregiver, searchable_caregivers(self.owner))
        self.delete(self.sitter)

        self.caregiver.refresh_from_db()
        self.assertFalse(self.caregiver.accepting_new_bookings)
        self.assertNotIn(
            self.caregiver, searchable_caregivers(self.owner, available_only=False)
        )
        pending.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(pending.status, Booking.Status.DECLINED)
        self.assertEqual(accepted.status, Booking.Status.CANCELLED)

    def test_other_accounts_are_untouched(self):
        self.delete(self.owner)
        self.other_owner.refresh_from_db()
        self.sitter.refresh_from_db()
        self.assertTrue(self.other_owner.is_active)
        self.assertTrue(self.sitter.is_active)
