"""Tests for the Find caregivers page (story #33). GeoSearch is always mocked."""

import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from caregivers.geocoding import GeocodingUnavailable, Location
from caregivers.models import CaregiverProfile, CaregiverService, ServiceType
from caregivers.search import (
    caregivers_near,
    neighborhood,
    neighborhoods,
    searchable_caregivers,
)
from pets.models import PetType

URL = reverse("caregiver_list")

# 70 Washington Square South (Greenwich Village).
NYU = {"lat": "40.729", "lng": "-73.997"}


class NeighborhoodDataTests(SimpleTestCase):
    def test_has_residential_neighborhoods_in_all_five_boroughs(self):
        rows = neighborhoods()
        self.assertGreater(len(rows), 150)
        self.assertEqual(
            {r["borough"] for r in rows},
            {"Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"},
        )

    def test_every_center_is_inside_nyc(self):
        for row in neighborhoods():
            self.assertTrue(40.4 < row["latitude"] < 41.0, row)
            self.assertTrue(-74.3 < row["longitude"] < -73.6, row)

    def test_lookup_by_code(self):
        village = neighborhood("MN0202")
        self.assertEqual(village["name"], "Greenwich Village")
        self.assertAlmostEqual(village["latitude"], 40.73, places=2)
        self.assertIsNone(neighborhood("XX9999"))


class SearchTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("owner", password="pw-12345!")
        cls.dog = PetType.objects.get_or_create(name="Dog")[0]
        cls.walking = ServiceType.objects.get_or_create(name="Dog walking")[0]
        # Distances are from NYU (40.729, -73.997).
        cls.village = cls.make("Chloe", "40.730", "-73.996", radius=3, hood="Greenwich Village")
        cls.midtown = cls.make("Alicia", "40.748", "-73.986", radius=3, hood="Midtown South")  # ~1.4 mi
        cls.lic = cls.make("Marcus", "40.742", "-73.936", radius=5, hood="Long Island City")  # ~3.3 mi
        cls.boerum = cls.make("Priya", "40.686", "-73.982", radius=1, hood="Boerum Hill")  # ~3.1 mi, radius 1
        cls.staten = cls.make("Sam", "40.643", "-74.074", radius=5, hood="St. George")  # ~7.2 mi, radius 5
        cls.village.supported_pet_types.add(cls.dog)
        CaregiverService.objects.create(
            caregiver=cls.village, service_type=cls.walking,
            price=Decimal("25.00"), price_unit="walk", is_active=True,
        )

    @classmethod
    def make(cls, name, lat, lng, radius=3, hood="", user=True, **fields):
        account = (
            get_user_model().objects.create_user(f"cg-{name.lower()}", password="pw-12345!")
            if user else None
        )
        return CaregiverProfile.objects.create(
            user=account, name=name, service_area=hood, neighborhood=hood,
            address="private address", latitude=Decimal(lat), longitude=Decimal(lng),
            service_radius_miles=radius, **fields,
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def names(self, response):
        return [c.name for c in response.context["caregivers"]]


class CaregiversNearTests(SearchTestData):
    def test_only_caregivers_who_travel_that_far_nearest_first(self):
        results = caregivers_near(searchable_caregivers(self.owner), 40.729, -73.997)
        self.assertEqual([c.name for c in results], ["Chloe", "Alicia", "Marcus"])
        self.assertLess(results[0].distance, 0.2)
        self.assertAlmostEqual(results[1].distance, 1.4, delta=0.2)

    def test_caregiver_without_coordinates_is_left_out(self):
        self.make("NoMap", "40.730", "-73.996")
        CaregiverProfile.objects.filter(name="NoMap").update(latitude=None, longitude=None)
        results = caregivers_near(searchable_caregivers(self.owner), 40.729, -73.997)
        self.assertNotIn("NoMap", [c.name for c in results])


class FindCaregiversPageTests(SearchTestData):
    def test_login_required(self):
        self.client.logout()
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 302)

    def test_nav_link_points_here(self):
        response = self.client.get(reverse("pets:list"))
        self.assertContains(response, f'href="{URL}"')

    def test_without_a_location_lists_everyone_by_name(self):
        response = self.client.get(URL)
        self.assertEqual(self.names(response), ["Alicia", "Chloe", "Marcus", "Priya", "Sam"])
        self.assertContains(response, "Greenwich Village")
        self.assertNotContains(response, "mi away")

    def test_hides_caregivers_who_cannot_take_requests(self):
        self.make("NoAccount", "40.730", "-73.996", user=False)
        self.make("Busy", "40.730", "-73.996", accepting_new_bookings=False)
        response = self.client.get(URL)
        self.assertNotIn("NoAccount", self.names(response))
        self.assertNotIn("Busy", self.names(response))

    def test_caregiver_does_not_see_their_own_profile(self):
        self.client.force_login(self.village.user)
        response = self.client.get(URL)
        self.assertNotIn("Chloe", self.names(response))

    def test_search_by_picked_address(self):
        response = self.client.get(URL, {"address": "70 Washington Square South", **NYU})
        self.assertEqual(self.names(response), ["Chloe", "Alicia", "Marcus"])
        self.assertContains(response, "3 caregivers near")
        self.assertContains(response, "1.4 mi away")

    def test_search_by_neighborhood(self):
        response = self.client.get(URL, {"area": "MN0202"})
        self.assertEqual(self.names(response)[0], "Chloe")
        self.assertContains(response, "Greenwich Village, Manhattan")

    def test_unknown_neighborhood_code(self):
        response = self.client.get(URL, {"area": "XX9999"})
        self.assertContains(response, "Choose a neighborhood from the list.")

    def test_no_matches_shows_a_message(self):
        # Rossville, Staten Island: nobody travels that far.
        response = self.client.get(URL, {"address": "Rossville", "lat": "40.551", "lng": "-74.212"})
        self.assertEqual(self.names(response), [])
        self.assertContains(response, "No caregivers near")

    def test_coordinates_outside_nyc_are_ignored(self):
        with mock.patch("caregivers.views.geocode", return_value=None):
            response = self.client.get(
                URL, {"address": "Boston", "lat": "42.36", "lng": "-71.06"}
            )
        self.assertContains(response, "couldn&#x27;t find that place")

    @mock.patch("caregivers.views.geocode")
    def test_typed_address_is_looked_up_when_not_picked(self, geocode):
        geocode.return_value = Location(
            latitude=Decimal("40.729"), longitude=Decimal("-73.997"),
            neighborhood="Greenwich Village", borough="Manhattan",
        )
        response = self.client.get(URL, {"address": "70 Washington Square South"})
        geocode.assert_called_once_with("70 Washington Square South")
        self.assertEqual(self.names(response), ["Chloe", "Alicia", "Marcus"])

    @mock.patch("caregivers.views.geocode", return_value=None)
    def test_address_not_found(self, geocode):
        response = self.client.get(URL, {"address": "1 Hudson Pl, Hoboken"})
        self.assertEqual(self.names(response), [])
        self.assertContains(response, "couldn&#x27;t find that place in New York City")

    @mock.patch("caregivers.views.geocode", side_effect=GeocodingUnavailable("down"))
    def test_service_down_falls_back_to_neighborhood_name(self, geocode):
        response = self.client.get(URL, {"address": "long island"})
        self.assertEqual(self.names(response), ["Marcus"])
        self.assertContains(response, "Address search is unavailable right now")

    def test_cards_link_to_profile_and_show_services(self):
        response = self.client.get(URL, {"address": "x", **NYU})
        self.assertContains(response, reverse("caregiver", args=[self.village.pk]))
        self.assertContains(response, "View profile")
        self.assertContains(response, 'title="$25.00 / Per Walk">Dog walking</li>')

    def test_map_data_has_results_but_never_addresses(self):
        response = self.client.get(URL, {"address": "x", **NYU})
        data = response.context["map_data"]
        self.assertEqual([p["name"] for p in data["points"]], ["Chloe", "Alicia", "Marcus"])
        self.assertEqual(data["origin"], {"latitude": 40.729, "longitude": -73.997})
        self.assertNotIn("private address", json.dumps(data))
        self.assertNotContains(response, "private address")

    def test_neighborhood_options_are_listed(self):
        response = self.client.get(URL)
        labels = [n["label"] for n in response.context["neighborhood_options"]]
        self.assertIn("Greenwich Village, Manhattan", labels)
        self.assertContains(response, 'id="neighborhood-options"')
