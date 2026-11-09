"""Buttons on the owner's My requests → Bookings rows (Figma "My requests (Bookings)")."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from reviews.models import Review

from ..models import Booking
from .test_bookings import BookingTestData

LIST_URL = reverse("bookings:booking_list")


class BookingRowButtonTests(BookingTestData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_active_booking_has_a_message_button(self):
        booking = self.make_booking(status=Booking.Status.PENDING)
        response = self.client.get(LIST_URL)
        self.assertContains(
            response, reverse("messaging:message_booking", args=[booking.pk])
        )

    def test_completed_booking_can_be_rated_once(self):
        past = timezone.now() - timedelta(days=2)
        booking = self.make_booking(
            status=Booking.Status.COMPLETED,
            start_time=past,
            end_time=past + timedelta(hours=1),
        )
        rate_url = reverse("reviews:create", args=[booking.pk])
        self.assertContains(self.client.get(LIST_URL), rate_url)

        Review.objects.create(
            booking=booking, author=self.owner, role=Review.Role.OWNER, rating=5
        )
        self.assertNotContains(self.client.get(LIST_URL), rate_url)
