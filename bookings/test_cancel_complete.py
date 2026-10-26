"""Acceptance tests for #43 Cancel Booking and #109 Mark Booking as Completed."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Booking
from .tests import BookingTestData

Status = Booking.Status


def cancel_url(booking):
    return reverse("bookings:booking_cancel", args=[booking.pk])


def complete_url(booking):
    return reverse("bookings:booking_complete", args=[booking.pk])


def started(**fields):
    """Times for care that started an hour ago and is still going."""
    start = timezone.now() - timedelta(hours=1)
    return {"start_time": start, "end_time": start + timedelta(hours=2), **fields}


class SitterTestData(BookingTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sitter = get_user_model().objects.create_user(
            "sitter", password="pw-12345!", first_name="Chloe"
        )
        cls.caregiver.user = cls.sitter
        cls.caregiver.save()


class CancelBookingTests(SitterTestData):
    """#43: the owner cancels an eligible booking after confirming."""

    def setUp(self):
        self.client.force_login(self.owner)

    def test_detail_page_offers_cancel_for_pending_and_accepted(self):
        for status in (Status.PENDING, Status.ACCEPTED):
            booking = self.make_booking(status=status)
            response = self.client.get(booking.get_absolute_url())
            self.assertContains(response, cancel_url(booking))

    def test_no_cancel_option_once_started_or_closed(self):
        bookings = [
            self.make_booking(status=Status.ACCEPTED, **started()),
            self.make_booking(status=Status.DECLINED),
            self.make_booking(status=Status.COMPLETED, **started()),
            self.make_booking(status=Status.CANCELLED),
        ]
        for booking in bookings:
            response = self.client.get(booking.get_absolute_url())
            self.assertNotContains(response, cancel_url(booking))

    def test_asks_for_confirmation_first(self):
        booking = self.make_booking()
        response = self.client.get(cancel_url(booking))
        self.assertContains(response, "Cancel this booking?")
        self.assertContains(response, "Keep booking")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Status.PENDING)

    def test_confirming_cancels_the_booking(self):
        booking = self.make_booking(status=Status.ACCEPTED)
        response = self.client.post(cancel_url(booking), follow=True)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Status.CANCELLED)
        self.assertContains(response, "Booking canceled.")
        self.assertContains(response, "You canceled this booking")

    def test_cancelled_booking_stays_in_history(self):
        booking = self.make_booking(status=Status.CANCELLED)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertIn(booking, response.context["history"])
        self.assertNotIn(booking, response.context["active"])

    def test_cannot_cancel_after_start_or_when_closed(self):
        for fields in (
            started(status=Status.ACCEPTED),
            {"status": Status.DECLINED},
            started(status=Status.COMPLETED),
        ):
            booking = self.make_booking(**fields)
            response = self.client.post(cancel_url(booking), follow=True)
            self.assertContains(response, "can no longer be canceled")
            booking.refresh_from_db()
            # A pending request whose start time passed is declined automatically.
            expected = (
                Status.DECLINED if fields["status"] == Status.PENDING else fields["status"]
            )
            self.assertEqual(booking.status, expected)

    def test_only_the_owner_can_cancel(self):
        booking = self.make_booking()
        for user in (self.other_owner, self.sitter):
            self.client.force_login(user)
            self.assertEqual(self.client.post(cancel_url(booking)).status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Status.PENDING)

    def test_signed_out_visitors_go_to_login(self):
        self.client.logout()
        booking = self.make_booking()
        response = self.client.post(cancel_url(booking))
        self.assertRedirects(
            response, f"{reverse('login')}?next={cancel_url(booking)}"
        )

    def test_caregiver_sees_the_cancellation(self):
        booking = self.make_booking(status=Status.ACCEPTED)
        self.client.post(cancel_url(booking))
        self.client.force_login(self.sitter)

        detail = self.client.get(booking.get_absolute_url())
        self.assertContains(detail, "Booking canceled.")
        self.assertContains(detail, "status-cancelled")

        panel = self.client.get(
            reverse("bookings:caregiver_requests"), {"status": "all", "b": booking.pk}
        )
        self.assertContains(panel, "canceled this booking")
        # A cancelled booking no longer counts as upcoming care.
        self.assertNotIn(booking, panel.context["upcoming"])

    def test_cancelling_frees_the_time_slot(self):
        booking = self.make_booking(status=Status.ACCEPTED)
        self.client.post(cancel_url(booking))
        same_time = self.make_booking(
            owner=self.other_owner,
            pet=self.other_pet,
            start_time=booking.start_time,
            end_time=booking.end_time,
        )
        self.client.force_login(self.sitter)
        self.client.post(
            reverse("bookings:booking_respond", args=[same_time.pk]),
            {"action": "accept"},
        )
        same_time.refresh_from_db()
        self.assertEqual(same_time.status, Status.ACCEPTED)


class MarkCompletedTests(SitterTestData):
    """#109: the caregiver marks accepted care as completed."""

    def setUp(self):
        self.client.force_login(self.sitter)

    def test_caregiver_can_complete_started_accepted_care(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        response = self.client.post(complete_url(booking), follow=True)
        self.assertContains(response, "Marked as completed.")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Status.COMPLETED)

    def test_care_is_completed_automatically_a_day_after_it_ends(self):
        def ended(hours_ago):
            end = timezone.now() - timedelta(hours=hours_ago)
            return self.make_booking(
                status=Status.ACCEPTED, start_time=end - timedelta(hours=1), end_time=end
            )

        overdue, recent = ended(25), ended(23)
        response = self.client.get(
            reverse("bookings:caregiver_requests"), {"status": "completed"}
        )
        overdue.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual(overdue.status, Status.COMPLETED)
        self.assertTrue(overdue.completed_automatically)
        self.assertEqual(recent.status, Status.ACCEPTED)
        self.assertContains(response, "Completed automatically 24 hours after the booking ended.")

    def test_completing_it_yourself_is_not_automatic(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        self.client.post(complete_url(booking))
        booking.refresh_from_db()
        self.assertFalse(booking.completed_automatically)

    def test_status_stays_completed_after_refresh(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        self.client.post(complete_url(booking))
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Care completed.")
        self.assertEqual(Booking.objects.get(pk=booking.pk).status, Status.COMPLETED)

    def test_button_only_shows_for_eligible_bookings(self):
        eligible = self.make_booking(status=Status.ACCEPTED, **started())
        future = self.make_booking(status=Status.ACCEPTED)
        self.assertContains(
            self.client.get(eligible.get_absolute_url()), complete_url(eligible)
        )
        self.assertNotContains(
            self.client.get(future.get_absolute_url()), complete_url(future)
        )
        panel = self.client.get(
            reverse("bookings:caregiver_requests"),
            {"status": "accepted", "b": eligible.pk},
        )
        self.assertContains(panel, complete_url(eligible))

    def test_only_accepted_care_that_started_can_be_completed(self):
        for fields in (
            {"status": Status.ACCEPTED},  # hasn't started yet
            started(status=Status.PENDING),
            started(status=Status.DECLINED),
            started(status=Status.CANCELLED),
        ):
            booking = self.make_booking(**fields)
            response = self.client.post(complete_url(booking), follow=True)
            self.assertContains(response, "Only accepted care that has started")
            booking.refresh_from_db()
            # A pending request whose start time passed is declined automatically.
            expected = (
                Status.DECLINED if fields["status"] == Status.PENDING else fields["status"]
            )
            self.assertEqual(booking.status, expected)

    def test_completed_booking_cannot_be_accepted_or_declined(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        self.client.post(complete_url(booking))
        for action in ("accept", "decline"):
            self.client.post(
                reverse("bookings:booking_respond", args=[booking.pk]),
                {"action": action},
            )
            booking.refresh_from_db()
            self.assertEqual(booking.status, Status.COMPLETED)

    def test_only_the_caregiver_can_complete(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        for user in (self.owner, self.other_owner):
            self.client.force_login(user)
            self.assertEqual(self.client.post(complete_url(booking)).status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Status.ACCEPTED)

    def test_get_is_not_allowed(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        self.assertEqual(self.client.get(complete_url(booking)).status_code, 405)

    def test_unsafe_next_url_is_ignored(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        response = self.client.post(
            complete_url(booking), {"next": "https://evil.example.com/"}
        )
        self.assertRedirects(response, booking.get_absolute_url())

    def test_next_url_returns_to_the_requests_page(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        next_url = reverse("bookings:caregiver_requests") + "?status=accepted"
        response = self.client.post(complete_url(booking), {"next": next_url})
        self.assertRedirects(response, next_url)

    def test_owner_sees_completed_in_history(self):
        booking = self.make_booking(status=Status.ACCEPTED, **started())
        self.client.post(complete_url(booking))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertIn(booking, response.context["history"])
        self.assertContains(response, "status-completed")
        detail = self.client.get(booking.get_absolute_url())
        self.assertContains(detail, "Care completed.")

    def test_completed_tab_lists_completed_care(self):
        booking = self.make_booking(status=Status.COMPLETED, **started())
        response = self.client.get(
            reverse("bookings:caregiver_requests"), {"status": "completed"}
        )
        self.assertEqual(response.context["bookings"], [booking])
        self.assertContains(response, "You completed this booking.")

    def test_completed_care_keeps_its_time_slot(self):
        # #73: completing a booking doesn't reopen its time slot.
        done = self.make_booking(status=Status.COMPLETED, **started())
        overlapping = self.make_booking(
            owner=self.other_owner,
            pet=self.other_pet,
            start_time=timezone.now() + timedelta(minutes=10),
            end_time=done.end_time + timedelta(hours=1),
        )
        response = self.client.post(
            reverse("bookings:booking_respond", args=[overlapping.pk]),
            {"action": "accept"},
            follow=True,
        )
        self.assertContains(response, "overlaps this time")
        overlapping.refresh_from_db()
        self.assertEqual(overlapping.status, Status.PENDING)
