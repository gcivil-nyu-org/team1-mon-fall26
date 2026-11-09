"""Explore nearby (Figma "View Nearby Pet-Friendly Locations", "View Nearby Dog
Parks" and "(No result)" frames). Address lookups are mocked."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from caregivers.geocoding import GeocodingUnavailable, Location
from places.models import MAX_REPORT_LENGTH, Place, PlaceReport

EXPLORE = reverse("places:explore")
CAREGIVERS = reverse("caregiver_list")


class ExploreData(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Start from just these places, not the NYC Open Data snapshot.
        Place.objects.all().delete()
        cls.owner = get_user_model().objects.create_user("arian", password="pw-12345!")

        def add(name, category, lat, lng, **extra):
            return Place.objects.create(
                name=name, category=category, latitude=lat, longitude=lng, **extra
            )

        # Around Park Slope (center 40.6727, -73.9787).
        cls.cafe = add(
            "Bark & Brew Café",
            "cafe",
            "40.6716",
            "-73.9780",
            address="214 7th Ave",
            borough="Brooklyn",
            hours="Open daily 8 AM – 6 PM",
            features="Dogs welcome on the patio\nWater bowls and treats",
        )
        cls.park = add(
            "Washington Park Dog Run",
            "dog_park",
            "40.6730",
            "-73.9860",
            neighborhood="Park Slope",
            borough="Brooklyn",
            source=Place.Source.NYC_PARKS,
            source_id="B163-DOGAREA0001",
            features="Fenced off-leash dog run",
        )
        cls.store = add("Slope Pet Supply", "pet_store", "40.6684", "-73.9867")
        # Far away, in the Bronx.
        cls.bronx = add("Starlight Park Dog Run", "dog_park", "40.8304", "-73.8836")
        cls.hidden = add("Closed Café", "cafe", "40.6720", "-73.9785", is_active=False)

    def setUp(self):
        self.client.force_login(self.owner)

    def names(self, response):
        return [p.name for p in response.context["places"]]


class PlaceModelTests(ExploreData):
    def test_display_helpers(self):
        self.assertEqual(str(self.cafe), "Bark & Brew Café")
        self.assertEqual(self.cafe.place_line(), "214 7th Ave, Brooklyn")
        self.assertEqual(self.park.place_line(), "Park Slope, Brooklyn")
        self.assertEqual(self.store.place_line(), "")
        self.assertEqual(
            self.cafe.feature_list(),
            ["Dogs welcome on the patio", "Water bowls and treats"],
        )
        self.assertIn("destination=40.6716,-73.9780", self.cafe.directions_url())
        report = PlaceReport.objects.create(
            place=self.cafe, reporter=self.owner, details="Closed on Mondays now."
        )
        self.assertEqual(str(report), "Bark & Brew Café: Closed on Mondays now.")


class ViewNearbyPlacesTests(ExploreData):
    """View Nearby Pet-Friendly Locations."""

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(EXPLORE).status_code, 302)

    def test_without_a_location_every_place_is_listed(self):
        response = self.client.get(EXPLORE)
        self.assertEqual(
            self.names(response),
            [
                "Bark & Brew Café",
                "Slope Pet Supply",
                "Starlight Park Dog Run",
                "Washington Park Dog Run",
            ],
        )
        self.assertContains(response, "4 places in New York City")
        self.assertNotContains(response, "Closed Café")

    def test_places_near_a_neighborhood_closest_first(self):
        response = self.client.get(EXPLORE, {"location": "Park Slope", "distance": "1"})
        self.assertEqual(
            self.names(response),
            ["Bark & Brew Café", "Washington Park Dog Run", "Slope Pet Supply"],
        )
        self.assertContains(response, "3 places near Park Slope")
        self.assertContains(response, "0.1 mi away")
        # The list: address first, as in the design. The distance never wraps
        # or gets cut off, so a long address can't hide it.
        distance = '<span class="place-distance">{} mi</span>'
        self.assertContains(
            response, "<span>214 7th Ave · " + distance.format("0.1") + "</span>"
        )
        self.assertContains(
            response, "<span>Park Slope · " + distance.format("0.3") + "</span>"
        )
        self.assertContains(response, "<span>" + distance.format("0.4") + "</span>")
        self.assertEqual(response.context["distance"], 1)

    def test_distance_choice(self):
        response = self.client.get(
            EXPLORE, {"location": "Park Slope", "distance": "10"}
        )
        self.assertEqual(response.context["distance"], 10)
        self.assertNotIn("Starlight Park Dog Run", self.names(response))  # 11 mi away
        response = self.client.get(EXPLORE, {"location": "Park Slope", "distance": "7"})
        self.assertEqual(response.context["distance"], 1)  # not a choice: default

    def test_zip_code(self):
        response = self.client.get(EXPLORE, {"location": "11215"})
        self.assertIn("Bark & Brew Café", self.names(response))

    def test_the_first_place_is_picked_and_shown_in_the_card(self):
        response = self.client.get(EXPLORE, {"location": "Park Slope"})
        self.assertEqual(response.context["selected"], self.cafe)
        html = response.content.decode()
        card = html.split(f'data-place="{self.cafe.pk}" aria-label')[1].split(
            "</article>"
        )[0]
        self.assertIn("214 7th Ave, Brooklyn", card)
        self.assertIn("Open daily 8 AM – 6 PM", card)
        self.assertIn("Water bowls and treats", card)
        self.assertIn("Get directions", card)
        self.assertIn("Report wrong info", card)
        self.assertIn("Source: PawPal team", card)

    def test_picking_another_place(self):
        response = self.client.get(
            EXPLORE, {"location": "Park Slope", "place": self.park.pk}
        )
        self.assertEqual(response.context["selected"], self.park)
        response = self.client.get(EXPLORE, {"location": "Park Slope", "place": "999"})
        self.assertEqual(response.context["selected"], self.cafe)

    def test_open_data_places_name_their_source(self):
        response = self.client.get(EXPLORE, {"place": self.park.pk})
        self.assertContains(response, "https://data.cityofnewyork.us/d/hxx3-bwgv")
        self.assertContains(response, ">NYC Open Data</a>")

    @override_settings(CARTO_BASEMAPS_KEY="")  # not whatever the terminal has
    def test_map_data(self):
        response = self.client.get(EXPLORE, {"location": "Park Slope"})
        data = response.context["map_data"]
        self.assertEqual(len(data["places"]), 3)
        self.assertEqual(data["selected"], self.cafe.pk)
        self.assertEqual(data["places"][0]["category"], "cafe")
        self.assertIsNotNone(data["origin"])
        self.assertContains(response, 'id="places-map-data"')
        self.assertEqual(data["carto_key"], "")

    @override_settings(CARTO_BASEMAPS_KEY="test-key")
    def test_carto_key_reaches_the_map(self):
        response = self.client.get(EXPLORE)
        self.assertEqual(response.context["map_data"]["carto_key"], "test-key")

    def test_category_chips(self):
        response = self.client.get(EXPLORE, {"location": "Park Slope", "place": "1"})
        labels = [c["label"] for c in response.context["chips"]]
        self.assertEqual(
            labels, ["All", "Dog parks", "Cafés", "Pet stores", "Restaurants"]
        )
        cafes = response.context["chips"][2]["query"]
        self.assertIn("category=cafe", cafes)
        self.assertIn("location=Park+Slope", cafes)
        self.assertNotIn("place=", cafes)

    def test_current_location(self):
        response = self.client.get(
            EXPLORE, {"here": "1", "lat": "40.672", "lng": "-73.979"}
        )
        self.assertContains(response, "near you (Park Slope)")
        self.assertEqual(response.context["location_text"], "")

    def test_current_location_outside_nyc(self):
        response = self.client.get(
            EXPLORE, {"here": "1", "lat": "34.05", "lng": "-118.2"}
        )
        self.assertContains(response, "isn&#x27;t in New York City")

    def test_suggestion_picked_in_the_browser(self):
        response = self.client.get(
            EXPLORE, {"location": "My street", "lat": "40.672", "lng": "-73.979"}
        )
        self.assertContains(response, "near My street")

    @mock.patch("places.search.geocode")
    def test_street_address(self, geocode):
        geocode.return_value = Location(
            Decimal("40.672"), Decimal("-73.979"), "Park Slope", "Brooklyn"
        )
        response = self.client.get(EXPLORE, {"location": "200 7th Ave"})
        self.assertContains(response, "near 200 7th Ave")

    @mock.patch("places.search.geocode", return_value=None)
    def test_unknown_address(self, geocode):
        response = self.client.get(EXPLORE, {"location": "Nowhere Street"})
        self.assertContains(response, "couldn&#x27;t find that place")

    @mock.patch("places.search.geocode", side_effect=GeocodingUnavailable("down"))
    def test_address_search_down(self, geocode):
        response = self.client.get(EXPLORE, {"location": "200 7th Ave"})
        self.assertContains(response, "Address search is unavailable")


class ViewDogParksTests(ExploreData):
    """View Dog Parks: the Dog parks chip."""

    def test_only_dog_parks(self):
        response = self.client.get(
            EXPLORE, {"location": "Park Slope", "category": "dog_park"}
        )
        self.assertEqual(self.names(response), ["Washington Park Dog Run"])
        self.assertContains(response, "1 dog park near Park Slope")
        self.assertContains(response, '<span class="place-badge">Dog park</span>')
        self.assertContains(response, 'aria-current="true">Dog parks</a>')

    def test_every_dog_park_in_the_city(self):
        response = self.client.get(EXPLORE, {"category": "dog_park"})
        self.assertContains(response, "2 dog parks in New York City")

    def test_unknown_category_shows_all(self):
        response = self.client.get(EXPLORE, {"category": "zoo"})
        self.assertEqual(response.context["category"], "")


class NoResultTests(ExploreData):
    def test_nothing_nearby(self):
        response = self.client.get(EXPLORE, {"location": "Astoria", "category": "cafe"})
        self.assertContains(response, "No cafés near Astoria")
        self.assertContains(response, "Search a nearby neighborhood or zip code.")
        self.assertContains(response, "Try another area")
        self.assertNotContains(response, 'id="places-map"')

    def test_no_places_of_that_kind(self):
        response = self.client.get(EXPLORE, {"category": "restaurant"})
        self.assertContains(response, "No restaurants on PawPal yet")
        self.assertContains(response, "Show all places")

    def test_no_places_at_all(self):
        Place.objects.all().delete()
        response = self.client.get(EXPLORE)
        self.assertContains(response, "No pet-friendly places yet")


class LookingForTests(ExploreData):
    """The "Looking for" menu switches between caregivers and places."""

    def test_places_to_caregivers_keeps_the_location(self):
        response = self.client.get(
            EXPLORE,
            {
                "looking_for": "caregivers",
                "location": "Park Slope",
                "distance": "2",
                "category": "cafe",
            },
        )
        self.assertRedirects(
            response,
            f"{CAREGIVERS}?location=Park+Slope&distance=2",
            fetch_redirect_response=False,
        )

    def test_caregivers_to_places(self):
        response = self.client.get(
            CAREGIVERS,
            {"looking_for": "places", "location": "Park Slope", "sort": "name"},
        )
        self.assertRedirects(
            response, f"{EXPLORE}?location=Park+Slope", fetch_redirect_response=False
        )

    def test_switch_without_a_search(self):
        response = self.client.get(CAREGIVERS, {"looking_for": "places"})
        self.assertRedirects(response, EXPLORE, fetch_redirect_response=False)

    def test_menu_on_both_pages(self):
        places = self.client.get(EXPLORE)
        self.assertContains(places, 'value="places" selected>Pet-friendly places')
        caregivers = self.client.get(CAREGIVERS)
        self.assertContains(caregivers, 'value="caregivers" selected>Caregivers')
        for response in (places, caregivers):
            self.assertContains(response, "Explore nearby")

    def test_explore_tab_is_active(self):
        response = self.client.get(EXPLORE)
        self.assertContains(response, 'class="active">Explore</a>')


class ReportWrongInfoTests(ExploreData):
    def url(self, place=None, **params):
        return reverse("places:report", args=[(place or self.cafe).pk])

    def test_form(self):
        response = self.client.get(self.url())
        self.assertContains(response, "Report wrong info")
        self.assertContains(response, "214 7th Ave, Brooklyn")

    def test_report(self):
        back = f"{EXPLORE}?location=Park+Slope&place={self.cafe.pk}"
        response = self.client.post(
            self.url(), {"details": " Closes at 5 PM now. ", "next": back}, follow=True
        )
        self.assertRedirects(response, back)
        report = PlaceReport.objects.get()
        self.assertEqual(report.details, "Closes at 5 PM now.")
        self.assertEqual(report.reporter, self.owner)
        self.assertFalse(report.is_resolved)
        self.assertContains(
            response, "Thanks! We&#x27;ll check the information for Bark"
        )

    def test_empty_or_too_long(self):
        response = self.client.post(self.url(), {"details": "  "})
        self.assertContains(response, "Tell us what&#x27;s wrong")
        response = self.client.post(
            self.url(), {"details": "x" * (MAX_REPORT_LENGTH + 1)}
        )
        self.assertContains(response, f"Keep it to {MAX_REPORT_LENGTH} characters.")
        self.assertFalse(PlaceReport.objects.exists())

    def test_back_link_must_stay_on_pawpal(self):
        response = self.client.post(
            self.url(), {"details": "Moved.", "next": "https://evil.example/"}
        )
        self.assertRedirects(
            response, f"{EXPLORE}?place={self.cafe.pk}", fetch_redirect_response=False
        )

    def test_hidden_places_cannot_be_reported(self):
        self.assertEqual(self.client.get(self.url(self.hidden)).status_code, 404)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)


class FigmaDetailsTests(ExploreData):
    """Small details from the Figma Pet-Friendly Locations frames."""

    def test_borough_is_shown_once(self):
        place = Place(address="214 7th Ave, Brooklyn", borough="Brooklyn")
        self.assertEqual(place.place_line(), "214 7th Ave, Brooklyn")
        self.assertEqual(Place(borough="Queens").place_line(), "Queens")

    def test_hours_read_open_today(self):
        self.assertEqual(
            Place(hours="8 AM – 6 PM").hours_line(), "Open today 8 AM – 6 PM"
        )
        self.assertEqual(
            Place(hours="Open daily 8 AM – 6 PM").hours_line(), "Open daily 8 AM – 6 PM"
        )
        self.assertEqual(Place().hours_line(), "")

    def test_source_says_verified(self):
        self.park.checked_on = date(2026, 11, 8)
        self.park.save()
        response = self.client.get(
            EXPLORE, {"location": "Park Slope", "place": self.park.pk}
        )
        self.assertContains(response, "verified Nov 8, 2026")
        self.assertNotContains(response, "checked Nov 8, 2026")

    def test_headings_name_the_area_as_typed(self):
        response = self.client.get(
            EXPLORE, {"location": "Carroll Gardens", "category": "cafe"}
        )
        self.assertEqual(response.context["origin_name"], "Carroll Gardens")
        self.assertContains(response, "<h2>No cafés near Carroll Gardens yet</h2>")
