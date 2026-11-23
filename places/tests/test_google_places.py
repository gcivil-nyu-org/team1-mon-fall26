"""Dog-friendly cafés and restaurants from Google Maps (places/google_places.py).
Requests to the Places API are mocked; answers look like Text Search's."""

import io
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from places import google_places
from places.google_places import (
    CACHE_DAYS,
    FIELD_MASK,
    GooglePlacesUnavailable,
    delete_old_places,
    refresh_near,
    search,
    update_google_places,
    weekly_hours,
)
from places.models import Place

EXPLORE = reverse("places:explore")
KEY = "test-key"
PARK_SLOPE = (40.6727, -73.9787)


def result(id="ChIJcafe", **fields):
    """One Text Search result: a dog-friendly café in Park Slope unless told
    otherwise."""
    base = {
        "id": id,
        "displayName": {"text": "Lucky Dog Café", "languageCode": "en"},
        "location": {"latitude": 40.6716, "longitude": -73.978},
        "primaryType": "coffee_shop",
        "allowsDogs": True,
        "outdoorSeating": True,
        "addressComponents": [
            {"longText": "214", "shortText": "214", "types": ["street_number"]},
            {"longText": "7th Avenue", "shortText": "7th Ave", "types": ["route"]},
            {"longText": "11215", "shortText": "11215", "types": ["postal_code"]},
        ],
        "regularOpeningHours": {
            "periods": [
                {
                    "open": {"day": day, "hour": 8, "minute": 0},
                    "close": {"day": day, "hour": 18, "minute": 30},
                }
                for day in range(1, 6)
            ]
        },
    }
    base.update(fields)
    return {k: v for k, v in base.items() if v is not None}


def answer(*results):
    return {"places": list(results)}


def respond(data):
    """What urlopen returns: a context manager with the JSON body."""
    body = io.BytesIO(json.dumps(data).encode())
    response = mock.MagicMock()
    response.__enter__.return_value = body
    return response


class HoursTests(SimpleTestCase):
    def test_weekdays_monday_first(self):
        week = weekly_hours(result()["regularOpeningHours"])
        self.assertEqual(week[:5], [{"open": "08:00", "close": "18:30"}] * 5)
        self.assertEqual(week[5:], [None, None])

    def test_sunday_is_last(self):
        hours = {
            "periods": [
                {
                    "open": {"day": 0, "hour": 10, "minute": 0},
                    "close": {"day": 0, "hour": 16, "minute": 0},
                }
            ]
        }
        self.assertEqual(weekly_hours(hours)[6], {"open": "10:00", "close": "16:00"})

    def test_past_midnight_kept(self):
        hours = {
            "periods": [
                {
                    "open": {"day": 5, "hour": 18, "minute": 0},
                    "close": {"day": 6, "hour": 2, "minute": 0},
                }
            ]
        }
        self.assertEqual(weekly_hours(hours)[4], {"open": "18:00", "close": "02:00"})

    def test_open_around_the_clock_not_shown(self):
        hours = {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]}
        self.assertEqual(weekly_hours(hours), [])

    def test_lunch_break_not_shown(self):
        morning = {
            "open": {"day": 1, "hour": 8, "minute": 0},
            "close": {"day": 1, "hour": 12, "minute": 0},
        }
        evening = {
            "open": {"day": 1, "hour": 17, "minute": 0},
            "close": {"day": 1, "hour": 22, "minute": 0},
        }
        self.assertEqual(weekly_hours({"periods": [morning, evening]}), [])

    def test_no_hours(self):
        self.assertEqual(weekly_hours(None), [])
        self.assertEqual(weekly_hours({}), [])


class ParseTests(SimpleTestCase):
    def test_dog_friendly_cafe(self):
        places, no_dogs = google_places.google_places(answer(result()))
        self.assertEqual(no_dogs, [])
        (place,) = places
        self.assertEqual(place["source_id"], "ChIJcafe")
        self.assertEqual(place["name"], "Lucky Dog Café")
        self.assertEqual(place["category"], Place.Category.CAFE)
        self.assertEqual(place["address"], "214 7th Ave")
        self.assertEqual(place["zip_code"], "11215")
        self.assertEqual(place["borough"], "Brooklyn")
        self.assertTrue(place["neighborhood"])
        self.assertEqual(place["latitude"], Decimal("40.671600"))
        self.assertEqual(place["features"], "Dogs welcome\nOutdoor seating")
        self.assertEqual(len(place["weekly_hours"]), 7)

    def test_restaurant(self):
        (place,), _ = google_places.google_places(
            answer(result(primaryType="italian_restaurant", outdoorSeating=False))
        )
        self.assertEqual(place["category"], Place.Category.RESTAURANT)
        self.assertEqual(place["features"], "Dogs welcome")

    def test_dogs_not_allowed_or_unknown(self):
        places, no_dogs = google_places.google_places(
            answer(
                result(id="no", allowsDogs=False), result(id="unknown", allowsDogs=None)
            )
        )
        self.assertEqual(places, [])
        self.assertEqual(no_dogs, ["no"])

    def test_left_out(self):
        places, _ = google_places.google_places(
            answer(
                result(id=None),
                result(id="noname", displayName={"text": "  "}),
                result(id="nowhere", location={}),
                result(id="boston", location={"latitude": 42.36, "longitude": -71.06}),
            )
        )
        self.assertEqual(places, [])

    def test_no_street(self):
        (place,), _ = google_places.google_places(answer(result(addressComponents=[])))
        self.assertEqual((place["address"], place["zip_code"]), ("", ""))

    def test_empty_answer(self):
        self.assertEqual(google_places.google_places({}), ([], []))


@override_settings(GOOGLE_PLACES_API_KEY=KEY)
class SearchTests(SimpleTestCase):
    @mock.patch("places.google_places.urlopen")
    def test_request(self, urlopen):
        urlopen.return_value = respond(answer(result()))
        data = search("dog friendly cafe", "cafe", 40.6727, -73.9787, 1)
        self.assertEqual(data["places"][0]["id"], "ChIJcafe")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, google_places.SEARCH_URL)
        self.assertEqual(request.get_header("X-goog-api-key"), KEY)
        self.assertEqual(request.get_header("X-goog-fieldmask"), FIELD_MASK)
        self.assertIn("places.allowsDogs", FIELD_MASK)
        body = json.loads(request.data)
        self.assertEqual(body["textQuery"], "dog friendly cafe")
        self.assertEqual(body["includedType"], "cafe")
        box = body["locationRestriction"]["rectangle"]
        self.assertLess(box["low"]["latitude"], 40.6727)
        self.assertGreater(box["high"]["longitude"], -73.9787)

    @mock.patch("places.google_places.urlopen", side_effect=URLError("down"))
    def test_unavailable(self, urlopen):
        with self.assertRaises(GooglePlacesUnavailable):
            search("dog friendly cafe", "cafe", 40.6727, -73.9787, 1)


def row(**fields):
    (place,), _ = google_places.google_places(answer(result(**fields)))
    return place


class UpdateTests(TestCase):
    def setUp(self):
        Place.objects.all().delete()
        self.today = date(2026, 11, 23)

    def test_adds_then_refreshes(self):
        self.assertEqual(update_google_places([row()], [], self.today), (1, 0, 0))
        place = Place.objects.get(source=Place.Source.GOOGLE)
        self.assertEqual(place.checked_on, self.today)
        later = self.today + timedelta(days=3)
        changed = row(displayName={"text": "Lucky Dog Coffee"})
        self.assertEqual(update_google_places([changed], [], later), (0, 1, 0))
        place.refresh_from_db()
        self.assertEqual((place.name, place.checked_on), ("Lucky Dog Coffee", later))

    def test_no_longer_allows_dogs_is_hidden(self):
        update_google_places([row()], [], self.today)
        self.assertEqual(update_google_places([], ["ChIJcafe"], self.today), (0, 0, 1))
        self.assertFalse(Place.objects.get(source_id="ChIJcafe").is_active)

    def test_admin_edits_kept(self):
        update_google_places([row()], [], self.today)
        Place.objects.update(name="Fixed name", edited_at=timezone.now())
        update_google_places([row()], ["ChIJcafe"], self.today)
        place = Place.objects.get(source_id="ChIJcafe")
        self.assertEqual(place.name, "Fixed name")
        self.assertTrue(place.is_active)

    def test_old_places_deleted(self):
        update_google_places([row()], [], self.today - timedelta(days=CACHE_DAYS + 1))
        update_google_places([row(id="fresh")], [], self.today)
        update_google_places([row(id="edited")], [], self.today - timedelta(days=90))
        Place.objects.filter(source_id="edited").update(edited_at=timezone.now())
        self.assertEqual(delete_old_places(self.today), 1)
        self.assertEqual(
            set(Place.objects.values_list("source_id", flat=True)), {"fresh", "edited"}
        )

    def test_source_link_and_name(self):
        update_google_places([row()], [], self.today)
        place = Place.objects.get(source_id="ChIJcafe")
        self.assertEqual(place.source_name(), "Google Maps")
        self.assertIn("query_place_id=ChIJcafe", place.source_url())
        self.assertTrue(place.source_url().startswith("https://www.google.com/maps/"))


@override_settings(GOOGLE_PLACES_API_KEY=KEY)
class RefreshTests(TestCase):
    def setUp(self):
        Place.objects.all().delete()
        cache.clear()

    @mock.patch("places.google_places.search")
    def test_all_asks_for_cafes_and_restaurants(self, search):
        search.return_value = answer(result())
        refresh_near(*PARK_SLOPE, 1)
        self.assertEqual(
            [c.args[1] for c in search.call_args_list], ["cafe", "restaurant"]
        )
        self.assertEqual(Place.objects.filter(source=Place.Source.GOOGLE).count(), 1)

    @mock.patch("places.google_places.search")
    def test_one_category(self, search):
        search.return_value = answer()
        refresh_near(*PARK_SLOPE, 1, Place.Category.RESTAURANT)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(
            search.call_args.args[:2], ("dog friendly restaurant", "restaurant")
        )

    @mock.patch("places.google_places.search")
    def test_other_categories_not_asked(self, search):
        refresh_near(*PARK_SLOPE, 1, Place.Category.DOG_PARK)
        search.assert_not_called()

    @mock.patch("places.google_places.search")
    def test_same_area_not_asked_again(self, search):
        search.return_value = answer()
        refresh_near(*PARK_SLOPE, 1, Place.Category.CAFE)
        refresh_near(40.6729, -73.9790, 1, Place.Category.CAFE)
        self.assertEqual(search.call_count, 1)
        refresh_near(*PARK_SLOPE, 5, Place.Category.CAFE)
        self.assertEqual(search.call_count, 2)

    @mock.patch("places.google_places.search", side_effect=GooglePlacesUnavailable("x"))
    def test_failure_is_logged_and_asked_again_later(self, search):
        with self.assertLogs("places.google_places", "WARNING"):
            refresh_near(*PARK_SLOPE, 1, Place.Category.CAFE)
        search.side_effect = None
        search.return_value = answer()
        refresh_near(*PARK_SLOPE, 1, Place.Category.CAFE)
        self.assertEqual(search.call_count, 2)

    @override_settings(GOOGLE_PLACES_API_KEY="")
    @mock.patch("places.google_places.search")
    def test_without_a_key_nothing_is_asked(self, search):
        refresh_near(*PARK_SLOPE, 1)
        search.assert_not_called()


@override_settings(GOOGLE_PLACES_API_KEY=KEY)
class ExploreTests(TestCase):
    def setUp(self):
        Place.objects.all().delete()
        cache.clear()
        owner = get_user_model().objects.create_user("kat", password="pw-12345!")
        self.client.force_login(owner)

    @mock.patch("places.google_places.search")
    def test_cafe_found_by_google_is_listed(self, search):
        search.return_value = answer(result())
        response = self.client.get(
            EXPLORE, {"location": "Park Slope", "category": "cafe"}
        )
        self.assertEqual(
            [p.name for p in response.context["places"]], ["Lucky Dog Café"]
        )
        self.assertContains(response, "Google Maps")
        self.assertContains(response, "Dogs welcome")

    @mock.patch("places.google_places.search")
    def test_without_a_location_google_is_not_asked(self, search):
        self.client.get(EXPLORE, {"category": "cafe"})
        search.assert_not_called()

    @mock.patch("places.google_places.search", side_effect=GooglePlacesUnavailable("x"))
    def test_google_down_still_shows_the_page(self, search):
        with self.assertLogs("places.google_places", "WARNING"):
            response = self.client.get(EXPLORE, {"location": "Park Slope"})
        self.assertEqual(response.status_code, 200)
