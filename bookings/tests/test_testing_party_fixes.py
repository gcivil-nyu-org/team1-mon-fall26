"""Fixes for booking issues other teams found at the testing party: requests
outside the caregiver's services or open time (#297, #307), the same request
twice (#312), dates far ahead (#331, #332), care over several days (#318) and
the date/time search listing booked caregivers (#335, #345)."""

import json
from datetime import datetime, time, timedelta

from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.availability import covered_by_availability, day_pieces
from bookings.forms import BookingRequestForm
from bookings.models import Booking
from bookings.templatetags.booking_tags import care_date, care_span
from caregivers.models import (
    CaregiverAvailability,
    CaregiverProfile,
    CaregiverService,
)
from caregivers.search import available_during

from .test_bookings import BookingTestData, times


def local(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class RequestChecksTests(BookingTestData):
    def form(self, **overrides):
        return BookingRequestForm(data=self.form_data(**overrides), owner=self.owner)

    def test_caregiver_without_services_cannot_be_requested(self):
        CaregiverService.objects.filter(caregiver=self.caregiver).delete()
        form = self.form()
        self.assertFalse(form.is_valid())
        self.assertIn(
            "hasn't listed any services", " ".join(form.errors["service_type"])
        )

    def test_time_outside_availability_is_refused(self):
        day = timezone.localdate() + timedelta(days=3)
        CaregiverAvailability.objects.filter(caregiver=self.caregiver, date=day).update(
            start_time=time(9), end_time=time(12)
        )
        form = self.form(**times(local(day, 22), local(day, 23)))
        self.assertFalse(form.is_valid())
        self.assertIn("isn't available then", " ".join(form.errors["start_time"]))
        self.assertTrue(
            self.form(**times(local(day, 10), local(day, 11))).is_valid(),
        )

    def test_day_off_is_refused(self):
        day = timezone.localdate() + timedelta(days=3)
        CaregiverAvailability.objects.filter(
            caregiver=self.caregiver, date=day
        ).delete()
        form = self.form(**times(local(day, 10), local(day, 11)))
        self.assertFalse(form.is_valid())

    def test_overnight_care_needs_both_days_open(self):
        day = timezone.localdate() + timedelta(days=3)
        start, end = local(day, 20), local(day + timedelta(days=1), 8)
        self.assertTrue(self.form(**times(start, end)).is_valid())
        CaregiverAvailability.objects.filter(
            caregiver=self.caregiver, date=day + timedelta(days=1)
        ).update(start_time=time(9))
        self.assertFalse(self.form(**times(start, end)).is_valid())

    def test_same_request_again_is_refused(self):
        form = self.form()
        self.assertTrue(form.is_valid())
        booking = form.save(commit=False)
        booking.owner = self.owner
        booking.save()
        form.save_m2m()
        again = self.form()
        self.assertFalse(again.is_valid())
        self.assertIn("already have a request", " ".join(again.non_field_errors()))

    def test_far_future_and_very_long_requests_are_refused(self):
        far = timezone.localtime() + timedelta(days=400)
        form = self.form(**times(far, far + timedelta(hours=1)))
        self.assertFalse(form.is_valid())
        self.assertIn("within the next year", " ".join(form.errors["start_time"]))
        start = timezone.localtime() + timedelta(days=2)
        form = self.form(**times(start, start + timedelta(days=31)))
        self.assertFalse(form.is_valid())
        self.assertIn("up to 30 days", " ".join(form.errors["end_time"]))

    def test_last_minute_of_year_9999_is_a_form_error(self):
        response_form = self.form(
            start_time_0="9999-12-31",
            start_time_1="22:00",
            end_time_0="9999-12-31",
            end_time_1="23:30",
        )
        self.assertFalse(response_form.is_valid())


class AvailabilityHelperTests(TestCase):
    def test_day_pieces(self):
        day = timezone.localdate()
        pieces = day_pieces(local(day, 19, 8), local(day + timedelta(days=1), 22, 8))
        self.assertEqual(
            pieces,
            [
                (day, time(19, 8), None),
                (day + timedelta(days=1), time(0), time(22, 8)),
            ],
        )

    def test_covered(self):
        caregiver = CaregiverProfile.objects.create(name="Sam")
        day = timezone.localdate() + timedelta(days=1)
        CaregiverAvailability.objects.create(
            caregiver=caregiver, date=day, start_time=time(9), end_time=time(17)
        )
        self.assertTrue(
            covered_by_availability(caregiver, local(day, 9), local(day, 17))
        )
        self.assertFalse(
            covered_by_availability(caregiver, local(day, 8), local(day, 10))
        )


class DisplayTests(BookingTestData):
    def test_year_shown_only_when_not_this_year(self):
        this_year = local(timezone.localdate(), 10)
        self.assertNotIn(str(this_year.year), care_date(this_year))
        later = this_year.replace(year=2140)
        self.assertIn("2140", care_date(later, "D, M j · g:i A"))
        self.assertEqual(care_date(None), "")

    def test_span_over_two_days_names_the_end_date(self):
        day = timezone.localdate() + timedelta(days=1)
        booking = self.make_booking(
            start_time=local(day, 19, 8),
            end_time=local(day + timedelta(days=1), 22, 8),
        )
        span = care_span(booking)
        self.assertIn("7:08 PM – ", span)
        self.assertIn((day + timedelta(days=1)).strftime("%b"), span)
        self.assertTrue(span.endswith("10:08 PM"))
        same_day = self.make_booking(start_time=local(day, 9), end_time=local(day, 10))
        self.assertTrue(care_span(same_day).endswith("9:00 AM – 10:00 AM"))

    def test_template_filter_loads(self):
        rendered = Template('{% load booking_tags %}{{ when|care_date:"M j" }}').render(
            Context({"when": local(timezone.localdate(), 9)})
        )
        self.assertTrue(rendered)

    def test_caregiver_calendar_shows_every_day_of_overnight_care(self):
        self.caregiver.user = self.other_owner
        self.caregiver.save()
        day = timezone.localdate() + timedelta(days=1)
        self.make_booking(
            start_time=local(day, 19),
            end_time=local(day + timedelta(days=1), 22),
            status=Booking.Status.ACCEPTED,
        )
        self.client.force_login(self.other_owner)
        response = self.client.get(reverse("manage_availability"))
        days = [b["date"] for b in json.loads(response.context["calendar_bookings"])]
        self.assertEqual(days, [day.isoformat(), (day + timedelta(days=1)).isoformat()])


class SearchSkipsBookedCaregiversTests(BookingTestData):
    def test_booked_time_is_not_free(self):
        day = timezone.localdate() + timedelta(days=2)
        everyone = CaregiverProfile.objects.filter(pk=self.caregiver.pk)
        self.assertEqual(
            list(available_during(everyone, day, time(10), time(11))),
            [self.caregiver],
        )
        self.make_booking(
            start_time=local(day, 10),
            end_time=local(day, 12),
            status=Booking.Status.ACCEPTED,
        )
        self.assertEqual(list(available_during(everyone, day, time(10), time(11))), [])
        self.assertEqual(
            list(available_during(everyone, day, time(13), time(14))),
            [self.caregiver],
        )
