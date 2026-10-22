"""Acceptance tests for the owner's side of a booking request:
#39 Specify Booking Details, #40 Attach Pet Profile to Booking,
#41 View Booking Status."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Booking
from .tests import FMT, BookingTestData

LIST_URL = reverse("bookings:booking_list")
CREATE_URL = reverse("bookings:booking_create")


class SpecifyBookingDetailsTests(BookingTestData):
    """#39: service, date and start time are chosen and shown on the request."""

    def setUp(self):
        self.client.force_login(self.owner)

    def test_form_offers_service_types_and_date_time_pickers(self):
        response = self.client.get(CREATE_URL)
        self.assertContains(response, "Dog walking")
        self.assertContains(response, "Pet sitting")
        self.assertContains(response, 'type="datetime-local"', count=2)

    def test_service_date_and_start_time_are_required(self):
        for field in ("service_type", "start_time"):
            response = self.client.post(CREATE_URL, self.form_data(**{field: ""}))
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Booking.objects.exists())

    def test_chosen_details_appear_on_the_request(self):
        start = (timezone.localtime() + timedelta(days=3)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
        response = self.client.post(
            CREATE_URL,
            self.form_data(
                service_type=self.sitting.pk,
                start_time=start.strftime(FMT),
                end_time=(start + timedelta(hours=2)).strftime(FMT),
            ),
            follow=True,
        )
        booking = Booking.objects.get()
        self.assertEqual(booking.service_type, self.sitting)
        self.assertEqual(timezone.localtime(booking.start_time), start)
        self.assertContains(response, "Biscuit · Pet sitting")
        self.assertContains(response, start.strftime("%b %-d, 9:30 AM"))
        self.assertContains(response, "11:30 AM")


class AttachPetProfileTests(BookingTestData):
    """#40: one of the owner's pets is attached and the caregiver can see it."""

    def setUp(self):
        self.client.force_login(self.owner)

    def test_cannot_submit_without_a_pet(self):
        response = self.client.post(CREATE_URL, self.form_data(pet=""))
        self.assertContains(response, "Choose one of your pets.")
        self.assertFalse(Booking.objects.exists())

    def test_selected_pet_is_attached(self):
        self.client.post(CREATE_URL, self.form_data())
        self.assertEqual(Booking.objects.get().pet, self.pet)

    def test_caregiver_can_see_the_attached_pet(self):
        sitter = get_user_model().objects.create_user("sitter", password="pw-12345!")
        self.caregiver.user = sitter
        self.caregiver.save()
        self.pet.special_care_instructions = "Allergic to chicken."
        self.pet.save()
        booking = self.make_booking()
        self.client.force_login(sitter)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "About Biscuit")
        self.assertContains(response, "Dog")
        self.assertContains(response, "Allergic to chicken.")


class ViewBookingStatusTests(BookingTestData):
    """#41: every status is shown, and finished requests stay in the history."""

    def setUp(self):
        self.client.force_login(self.owner)

    def past_booking(self, **fields):
        start = timezone.now() - timedelta(days=2)
        return self.make_booking(start_time=start, end_time=start + timedelta(hours=1), **fields)

    def test_all_five_statuses_are_shown(self):
        for status in Booking.Status:
            self.make_booking(status=status)
        response = self.client.get(LIST_URL)
        for label in ("Pending", "Accepted", "Declined", "Cancelled", "Completed"):
            self.assertContains(response, f"</span>{label}</span>")

    def test_pending_and_upcoming_accepted_are_active(self):
        pending = self.make_booking()
        accepted = self.make_booking(status=Booking.Status.ACCEPTED)
        response = self.client.get(LIST_URL)
        self.assertEqual(set(response.context["active"]), {pending, accepted})
        self.assertEqual(list(response.context["history"]), [])

    def test_completed_declined_cancelled_and_past_care_are_history(self):
        completed = self.past_booking(status=Booking.Status.COMPLETED)
        declined = self.make_booking(status=Booking.Status.DECLINED)
        cancelled = self.make_booking(status=Booking.Status.CANCELLED)
        ended = self.past_booking(status=Booking.Status.ACCEPTED)
        response = self.client.get(LIST_URL)
        self.assertEqual(list(response.context["active"]), [])
        self.assertEqual(
            set(response.context["history"]), {completed, declined, cancelled, ended}
        )
        self.assertContains(response, "History")

    def test_active_soonest_first_history_newest_first(self):
        later = self.make_booking(start_time=timezone.now() + timedelta(days=5),
                                  end_time=timezone.now() + timedelta(days=5, hours=1))
        sooner = self.make_booking()
        old = self.past_booking(status=Booking.Status.COMPLETED)
        older = self.make_booking(
            status=Booking.Status.COMPLETED,
            start_time=timezone.now() - timedelta(days=9),
            end_time=timezone.now() - timedelta(days=9, hours=-1),
        )
        response = self.client.get(LIST_URL)
        self.assertEqual(list(response.context["active"]), [sooner, later])
        self.assertEqual(list(response.context["history"]), [old, older])

    def test_status_updates_when_caregiver_responds(self):
        booking = self.make_booking()
        Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.ACCEPTED)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Request accepted.")

    def test_completed_booking_says_so(self):
        booking = self.past_booking(status=Booking.Status.COMPLETED)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Care completed.")

    def test_cancelled_booking_says_so(self):
        booking = self.make_booking(status=Booking.Status.CANCELLED)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Request cancelled.")

    def test_no_active_requests_message(self):
        self.past_booking(status=Booking.Status.COMPLETED)
        response = self.client.get(LIST_URL)
        self.assertContains(response, "No pending or upcoming care right now.")
