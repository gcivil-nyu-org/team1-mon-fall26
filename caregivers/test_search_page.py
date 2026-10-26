"""Find caregivers page as designed in Figma ("Search Caregivers" frames):
one Location box (neighborhood, ZIP code or address), Distance, "Use my
current location", sorting, the map toggle and the no-results card."""

from unittest import mock, skip

from django.test import SimpleTestCase

from caregivers.search import find_neighborhood, find_zip_code, zip_codes
from caregivers.templatetags.caregiver_tags import experience_range, initials, place_name

from .test_search import NYU, URL, SearchTestData


class LocationLookupTests(SimpleTestCase):
    def test_neighborhood_names(self):
        cases = {
            "Park Slope": "Park Slope",
            "park slope, brooklyn": "Park Slope",
            "  Greenwich   Village ": "Greenwich Village",
            "South Slope": "Windsor Terrace-South Slope",  # part of a combined name
            "Astoria, Queens": "Astoria (Central)",  # without the "(Central)"
        }
        for text, name in cases.items():
            self.assertEqual(find_neighborhood(text)["name"], name, text)

    def test_unknown_or_wrong_borough(self):
        for text in ("Paris", "Park Slope, Queens", "", ","):
            self.assertIsNone(find_neighborhood(text), text)

    def test_zip_codes(self):
        place = find_zip_code("11215")
        self.assertEqual(place["label"], "11215 (Windsor Terrace-South Slope)")
        self.assertAlmostEqual(place["latitude"], 40.66, places=2)
        for text in ("07030", "1121", "abcde", "112150"):
            self.assertIsNone(find_zip_code(text), text)

    def test_zip_data_covers_all_five_boroughs(self):
        rows = zip_codes()
        self.assertGreater(len(rows), 170)
        self.assertEqual(
            {r["borough"] for r in rows.values()},
            {"Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"},
        )
        for row in rows.values():
            self.assertTrue(40.4 < row["latitude"] < 41.0)
            self.assertTrue(-74.3 < row["longitude"] < -73.6)


class CardHelperTests(SimpleTestCase):
    def test_initials(self):
        self.assertEqual(initials("Chloe Shih"), "CS")
        self.assertEqual(initials("Mary Ann Lee"), "ML")
        self.assertEqual(initials("Sam"), "S")
        self.assertEqual(initials(""), "?")

    def test_experience_ranges(self):
        self.assertEqual(experience_range(0), "Under 1 year")
        self.assertEqual(experience_range(2), "1–2 years")
        self.assertEqual(experience_range(4), "3–5 years")
        self.assertEqual(experience_range(9), "5+ years")


class SearchPageTests(SearchTestData):
    def test_page_matches_the_design(self):
        response = self.client.get(URL)
        self.assertContains(response, "Find a caregiver nearby")
        self.assertContains(response, 'name="location"')
        self.assertContains(response, 'name="distance"')
        self.assertContains(response, "Use my current location")
        self.assertContains(response, '<option value="5" selected>5 mi</option>', html=True)
        # The old availability menu is gone (#35 now follows the profile setting).
        self.assertNotContains(response, 'id="filter-availability"')

    @mock.patch("caregivers.views.geocode")
    def test_typed_neighborhood_needs_no_lookup(self, geocode):
        response = self.client.get(URL, {"location": "greenwich village"})
        geocode.assert_not_called()
        self.assertEqual(self.names(response)[0], "Chloe")
        # The heading shows just the neighborhood, like the design.
        self.assertContains(response, "near Greenwich Village<")

    @mock.patch("caregivers.views.geocode")
    def test_zip_code_search(self, geocode):
        response = self.client.get(URL, {"location": "10012", "distance": "2"})
        geocode.assert_not_called()
        self.assertEqual(self.names(response), ["Chloe", "Alicia"])
        self.assertContains(response, "near 10012 (")

    @mock.patch("caregivers.views.geocode", return_value=None)
    def test_unknown_place(self, geocode):
        response = self.client.get(URL, {"location": "Hoboken"})
        geocode.assert_called_once_with("Hoboken")
        self.assertEqual(self.names(response), [])
        self.assertContains(response, "Try a neighborhood, ZIP code or street address.")

    def test_old_address_and_area_links_still_work(self):
        by_address = self.client.get(URL, {"address": "70 Washington Square South", **NYU})
        self.assertEqual(self.names(by_address), ["Chloe", "Alicia", "Marcus"])
        by_area = self.client.get(URL, {"area": "MN0202"})
        self.assertEqual(self.names(by_area)[0], "Chloe")

    def test_typed_text_stays_in_the_box(self):
        response = self.client.get(URL, {"location": "Park Slope"})
        self.assertContains(response, 'value="Park Slope"')


class DistanceTests(SearchTestData):
    def test_distance_limits_results(self):
        # Alicia is ~1.4 mi and Marcus ~3.3 mi from NYU.
        near = {"location": "NYU", **NYU}
        self.assertEqual(self.names(self.client.get(URL, {**near, "distance": "1"})), ["Chloe"])
        self.assertEqual(
            self.names(self.client.get(URL, {**near, "distance": "2"})), ["Chloe", "Alicia"]
        )
        self.assertEqual(
            self.names(self.client.get(URL, {**near, "distance": "5"})),
            ["Chloe", "Alicia", "Marcus"],
        )

    def test_caregiver_radius_still_applies(self):
        # Priya (~3.1 mi) only travels 1 mi, so a 10 mi search doesn't find her.
        response = self.client.get(URL, {"location": "NYU", **NYU, "distance": "10"})
        self.assertNotIn("Priya", self.names(response))

    def test_unknown_distance_uses_the_default(self):
        for value in ("3", "abc", "-1", ""):
            response = self.client.get(URL, {"location": "NYU", **NYU, "distance": value})
            self.assertEqual(response.context["distance"], 5)


class CurrentLocationTests(SearchTestData):
    def test_current_location_in_nyc(self):
        response = self.client.get(URL, {"here": "1", **NYU})
        self.assertEqual(self.names(response), ["Chloe", "Alicia", "Marcus"])
        self.assertContains(response, "near you (Greenwich Village)")
        # The box stays empty rather than showing coordinates.
        self.assertEqual(response.context["location_text"], "")

    def test_current_location_outside_nyc(self):
        response = self.client.get(URL, {"here": "1", "lat": "42.36", "lng": "-71.06"})
        self.assertContains(response, "current location isn&#x27;t in New York City")
        self.assertIsNone(response.context["origin"])

    def test_missing_coordinates(self):
        response = self.client.get(URL, {"here": "1"})
        self.assertContains(response, "current location isn&#x27;t in New York City")


class SortTests(SearchTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for caregiver, years in ((cls.village, 1), (cls.midtown, 8), (cls.lic, 4)):
            caregiver.years_of_experience = years
            caregiver.save()

    def test_closest_first_is_the_default(self):
        response = self.client.get(URL, {"location": "NYU", **NYU})
        self.assertEqual(self.names(response), ["Chloe", "Alicia", "Marcus"])

    def test_most_experienced(self):
        response = self.client.get(URL, {"location": "NYU", **NYU, "sort": "experience"})
        self.assertEqual(self.names(response), ["Alicia", "Marcus", "Chloe"])

    def test_by_name(self):
        response = self.client.get(URL, {"location": "NYU", **NYU, "sort": "name"})
        self.assertEqual(self.names(response), ["Alicia", "Chloe", "Marcus"])

    def test_closest_without_a_location_falls_back_to_name(self):
        response = self.client.get(URL, {"sort": "closest"})
        self.assertEqual(self.names(response), ["Alicia", "Chloe", "Marcus", "Priya", "Sam"])

    def test_unknown_sort(self):
        response = self.client.get(URL, {"sort": "price"})
        self.assertEqual(response.context["sort"], "closest")


class NoResultsTests(SearchTestData):
    def test_suggests_nearby_neighborhoods_with_caregivers(self):
        # Long Island City is ~0.5 mi from Marcus but a 1 mi search from
        # Astoria finds nobody; nearby neighborhoods with caregivers are offered.
        response = self.client.get(URL, {"location": "Astoria, Queens", "distance": "1"})
        self.assertEqual(self.names(response), [])
        self.assertContains(response, "No caregivers near")
        self.assertContains(response, "Try a nearby neighborhood or ZIP code.")
        suggestions = response.context["suggestions"]
        self.assertTrue(1 <= len(suggestions) <= 3)
        for hood in suggestions:
            self.assertContains(response, f"?area={hood['code']}&amp;distance=1")
            follow = self.client.get(URL, {"area": hood["code"], "distance": "1"})
            self.assertTrue(self.names(follow), hood["name"])

    def test_no_suggestions_when_nobody_is_around(self):
        response = self.client.get(
            URL, {"location": "Rossville", "lat": "40.551", "lng": "-74.212", "distance": "1"}
        )
        self.assertEqual(response.context["suggestions"], [])
        self.assertContains(response, "Try a larger distance")


# The map is hidden for now (the Figma design has none). Remove this when it comes back.
@skip("Map is hidden for now; see caregiver_list.html")
class MapToggleTests(SearchTestData):
    def test_map_is_hidden_by_default(self):
        response = self.client.get(URL)
        self.assertContains(response, 'id="map-panel" hidden')
        self.assertContains(response, "Show map")

    def test_map_can_start_open(self):
        response = self.client.get(URL, {"map": "1"})
        self.assertNotContains(response, 'id="map-panel" hidden')
        self.assertContains(response, "Hide map")
        self.assertContains(response, "with-map")


class PlaceNameTests(SimpleTestCase):
    def test_results_heading_drops_the_borough(self):
        self.assertEqual(place_name("Park Slope, Brooklyn"), "Park Slope")
        self.assertEqual(place_name("10012 (Greenwich Village)"), "10012 (Greenwich Village)")
