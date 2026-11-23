"""Fixes for care post issues other teams found at the testing party: past
posts (#298, #325, #346), the distance before a search (#299), the end time
(#301), places that can't be found (#311, #319), ZIP codes (#309, #334),
caregivers not taking bookings (#340), the caregiver bookmark (#310) and
dates far ahead (#331, #332)."""

from datetime import datetime, time, timedelta
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.geocoding import geocode
from caregivers.search import find_zip_code
from opportunities.forms import CareOpportunityForm
from opportunities.models import CareOpportunity, CareOpportunityInterest

from .test_explore_pets import BROWSE_URL, ExploreTestData


class PastPostTests(ExploreTestData):
    def setUp(self):
        self.client.force_login(self.sitter)
        start = timezone.now() - timedelta(hours=2)
        CareOpportunity.objects.filter(pk=self.nearby.pk).update(
            start_time=start, end_time=start + timedelta(hours=1)
        )

    def test_past_posts_are_not_listed(self):
        response = self.client.get(BROWSE_URL, {"location": "Park Slope"})
        self.assertNotIn(self.nearby, response.context["posts"])

    def test_no_interest_in_a_past_post(self):
        url = reverse("opportunities:interest", args=[self.nearby.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "time has already passed")
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_owner_sees_it_as_past(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:list"))
        self.assertContains(response, ">Past</span>")


class BrowseTests(ExploreTestData):
    def setUp(self):
        self.client.force_login(self.sitter)

    def test_unknown_place_lists_nothing(self):
        with mock.patch("places.search.geocode", return_value=None):
            response = self.client.get(
                BROWSE_URL, {"location": "QATwoNoSuchNeighborhood"}
            )
        self.assertEqual(response.context["posts"], [])
        self.assertContains(response, "couldn&#x27;t find that place")

    def test_post_saved_with_a_zip_code_is_found_nearby(self):
        CareOpportunity.objects.filter(pk=self.nearby.pk).update(location="11215")
        response = self.client.get(BROWSE_URL, {"location": "11215", "distance": "1"})
        self.assertIn(self.nearby, response.context["posts"])

    def test_not_accepting_bookings_cannot_show_interest(self):
        self.caregiver.accepting_new_bookings = False
        self.caregiver.save()
        url = reverse("opportunities:interest", args=[self.nearby.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Turn on Accepting new bookings")
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_owner_has_no_book_button_for_them(self):
        CareOpportunityInterest.objects.create(
            opportunity=self.nearby, caregiver=self.caregiver
        )
        self.client.force_login(self.owner)
        url = reverse("opportunities:list")
        response = self.client.get(url, {"post": self.nearby.pk})
        self.assertContains(response, ">Book</a>")
        self.caregiver.accepting_new_bookings = False
        self.caregiver.save()
        response = self.client.get(url, {"post": self.nearby.pk})
        self.assertNotContains(response, ">Book</a>")

    def test_caregiver_bookmark_opens_pets_needing_care(self):
        response = self.client.get(reverse("caregiver_list"), {"distance": "5"})
        self.assertRedirects(
            response, f"{BROWSE_URL}?distance=5", fetch_redirect_response=False
        )


class TimeRangeTests(ExploreTestData):
    def test_end_time_is_shown(self):
        day = timezone.localdate() + timedelta(days=3)
        start = timezone.make_aware(datetime.combine(day, time(14)))
        self.nearby.start_time = start
        self.nearby.end_time = start + timedelta(hours=1)
        self.assertTrue(self.nearby.time_range().endswith("2:00 PM – 3:00 PM"))
        self.nearby.end_time = start + timedelta(days=1)
        self.assertIn(day.strftime("%b"), self.nearby.time_range().split("–")[1])

    def test_year_shown_when_not_this_year(self):
        start = timezone.make_aware(datetime(2140, 11, 27, 10))
        self.nearby.start_time = start
        self.nearby.end_time = start + timedelta(hours=2)
        self.assertIn("2140", self.nearby.time_range())


class FormLimitTests(ExploreTestData):
    def form(self, start, end):
        return CareOpportunityForm(
            data={
                "pet": self.nearby.pet_id,
                "service_type": self.walking.pk,
                "location": "Park Slope",
                "start_date": start.date(),
                "start_clock": start.strftime("%H:%M"),
                "end_date": end.date(),
                "end_clock": end.strftime("%H:%M"),
            },
            owner=self.owner,
        )

    def test_far_future_is_refused(self):
        start = timezone.localtime() + timedelta(days=400)
        form = self.form(start, start + timedelta(hours=1))
        self.assertFalse(form.is_valid())
        self.assertIn("within the next year", str(form.non_field_errors()))

    def test_year_9999_late_evening_is_a_form_error(self):
        start = datetime(9999, 12, 31, 22)
        self.assertFalse(self.form(start, start.replace(hour=23, minute=30)).is_valid())

    def test_too_long_is_refused(self):
        start = timezone.localtime() + timedelta(days=2)
        self.assertFalse(self.form(start, start + timedelta(days=31)).is_valid())


class ZipCodeTests(SimpleTestCase):
    def test_placeholder_zip_is_not_a_place(self):
        self.assertIsNone(find_zip_code("99999"))
        self.assertIsNotNone(find_zip_code("10012"))

    @mock.patch("caregivers.geocoding._fetch")
    def test_bare_zip_code_uses_its_own_area(self, fetch):
        location = geocode("10012")
        fetch.assert_not_called()
        self.assertEqual(location.borough, "Manhattan")
        self.assertIn("SoHo", location.neighborhood)
        self.assertIsNone(geocode("99999"))
        self.assertIsNone(geocode("07030"))
