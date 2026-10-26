"""Tests for caregiver map locations: the GeoSearch lookup, the profile form
and the geocode_caregivers command. GeoSearch is always mocked."""

import io
import json
from decimal import Decimal
from unittest import mock
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .forms import CaregiverProfileForm
from .geocoding import GeocodingUnavailable, Location, distance_miles, geocode
from .models import CaregiverProfile

WASHINGTON_SQUARE = Location(
    latitude=Decimal("40.729"),
    longitude=Decimal("-73.997"),
    neighborhood="Greenwich Village",
    borough="Manhattan",
)
PARK_SLOPE = Location(
    latitude=Decimal("40.661"),
    longitude=Decimal("-73.989"),
    neighborhood="South Slope",
    borough="Brooklyn",
)


def geosearch_response(features):
    """A fake urlopen() result holding a GeoSearch JSON body."""
    body = io.BytesIO(json.dumps({"features": features}).encode())
    response = mock.MagicMock()
    response.__enter__.return_value = body
    return response


def feature(lng, lat, neighbourhood="Greenwich Village", borough="Manhattan",
            label="70 WASHINGTON SQUARE SOUTH, New York, NY, USA"):
    return {
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": {"neighbourhood": neighbourhood, "borough": borough, "label": label},
    }


class GeocodeTests(SimpleTestCase):
    @mock.patch("caregivers.geocoding.urlopen")
    def test_returns_rounded_location(self, urlopen):
        urlopen.return_value = geosearch_response([feature(-73.997217, 40.729437)])
        location = geocode("70 Washington Square South")
        self.assertEqual(location.latitude, Decimal("40.729"))
        self.assertEqual(location.longitude, Decimal("-73.997"))
        self.assertEqual(location.neighborhood, "Greenwich Village")
        self.assertEqual(location.borough, "Manhattan")

    @mock.patch("caregivers.geocoding.urlopen")
    def test_sends_the_address_and_asks_for_one_result(self, urlopen):
        urlopen.return_value = geosearch_response([feature(-73.99, 40.72)])
        geocode("  70 Washington Square South ")
        request = urlopen.call_args.args[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(query["text"], ["70 Washington Square South"])
        self.assertEqual(query["size"], ["1"])
        self.assertIn("timeout", urlopen.call_args.kwargs)

    @mock.patch("caregivers.geocoding.urlopen")
    def test_unknown_address_returns_none(self, urlopen):
        urlopen.return_value = geosearch_response([])
        self.assertIsNone(geocode("1 Nowhere Street, Hoboken"))

    @mock.patch("caregivers.geocoding.urlopen")
    def test_blank_address_does_not_call_the_service(self, urlopen):
        self.assertIsNone(geocode("   "))
        urlopen.assert_not_called()

    @mock.patch("caregivers.geocoding.urlopen", side_effect=URLError("down"))
    def test_network_error_raises_unavailable(self, urlopen):
        with self.assertRaises(GeocodingUnavailable):
            geocode("70 Washington Square South")

    @mock.patch("caregivers.geocoding.urlopen", side_effect=TimeoutError())
    def test_timeout_raises_unavailable(self, urlopen):
        with self.assertRaises(GeocodingUnavailable):
            geocode("70 Washington Square South")

    @mock.patch("caregivers.geocoding.urlopen")
    def test_bad_response_raises_unavailable(self, urlopen):
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(b"<html>error</html>")
        urlopen.return_value = response
        with self.assertRaises(GeocodingUnavailable):
            geocode("70 Washington Square South")


class DistanceTests(SimpleTestCase):
    def test_same_point_is_zero(self):
        self.assertEqual(distance_miles(40.729, -73.997, 40.729, -73.997), 0)

    def test_washington_square_to_empire_state_building(self):
        # About 1.3 miles in a straight line.
        miles = distance_miles(40.7308, -73.9973, 40.7484, -73.9857)
        self.assertAlmostEqual(miles, 1.34, delta=0.05)

    def test_accepts_decimals(self):
        miles = distance_miles(
            WASHINGTON_SQUARE.latitude, WASHINGTON_SQUARE.longitude,
            PARK_SLOPE.latitude, PARK_SLOPE.longitude,
        )
        self.assertAlmostEqual(miles, 4.7, delta=0.2)


class LocationFormTests(TestCase):
    def setUp(self):
        patcher = mock.patch("caregivers.forms.geocode", return_value=WASHINGTON_SQUARE)
        self.geocode = patcher.start()
        self.addCleanup(patcher.stop)

    def data(self, **overrides):
        data = {
            "first_name": "Chloe",
            "last_name": "Shih",
            "years_of_experience": 2,
            "address": "70 Washington Square South",
            "service_radius_miles": 3,
            "accepting_new_bookings": "on",
        }
        data.update(overrides)
        return data

    def test_saves_rounded_coordinates_and_neighborhood(self):
        form = CaregiverProfileForm(data=self.data())
        self.assertTrue(form.is_valid(), form.errors)
        caregiver = form.save()
        caregiver.refresh_from_db()
        self.assertEqual(caregiver.latitude, Decimal("40.729"))
        self.assertEqual(caregiver.longitude, Decimal("-73.997"))
        self.assertEqual(caregiver.neighborhood, "Greenwich Village")
        self.assertEqual(caregiver.address, "70 Washington Square South")

    def test_address_is_required(self):
        form = CaregiverProfileForm(data=self.data(address=""))
        self.assertFalse(form.is_valid())
        self.assertIn("address", form.errors)
        self.geocode.assert_not_called()

    def test_address_outside_nyc_is_rejected(self):
        self.geocode.return_value = None
        form = CaregiverProfileForm(data=self.data(address="1 Hudson Pl, Hoboken"))
        self.assertFalse(form.is_valid())
        self.assertIn("couldn't find this address", form.errors["address"][0])

    def test_service_down_still_saves_without_coordinates(self):
        self.geocode.side_effect = GeocodingUnavailable("down")
        form = CaregiverProfileForm(data=self.data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.geocoding_unavailable)
        caregiver = form.save()
        self.assertIsNone(caregiver.latitude)
        self.assertEqual(caregiver.address, "70 Washington Square South")

    def test_radius_defaults_to_three_and_is_limited(self):
        self.assertEqual(CaregiverProfile().service_radius_miles, 3)
        for bad in (0, 26):
            form = CaregiverProfileForm(data=self.data(service_radius_miles=bad))
            self.assertFalse(form.is_valid())
            self.assertIn("service_radius_miles", form.errors)

    def test_unchanged_address_is_not_looked_up_again(self):
        form = CaregiverProfileForm(data=self.data())
        form.is_valid()
        caregiver = form.save()
        self.geocode.reset_mock()
        form = CaregiverProfileForm(data=self.data(bio="New intro"), instance=caregiver)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.geocode.assert_not_called()

    def test_changed_address_is_looked_up_again(self):
        form = CaregiverProfileForm(data=self.data())
        form.is_valid()
        caregiver = form.save()
        self.geocode.return_value = PARK_SLOPE
        form = CaregiverProfileForm(
            data=self.data(address="7th Ave and 9th St, Brooklyn"), instance=caregiver
        )
        self.assertTrue(form.is_valid(), form.errors)
        caregiver = form.save()
        caregiver.refresh_from_db()
        self.assertEqual(caregiver.latitude, Decimal("40.661"))
        self.assertEqual(caregiver.neighborhood, "South Slope")

    def test_new_address_during_outage_clears_old_coordinates(self):
        form = CaregiverProfileForm(data=self.data())
        form.is_valid()
        caregiver = form.save()
        self.geocode.side_effect = GeocodingUnavailable("down")
        form = CaregiverProfileForm(
            data=self.data(address="7th Ave and 9th St, Brooklyn"), instance=caregiver
        )
        self.assertTrue(form.is_valid(), form.errors)
        caregiver = form.save()
        self.assertIsNone(caregiver.latitude)
        self.assertEqual(caregiver.neighborhood, "")


class LocationViewTests(TestCase):
    def setUp(self):
        patcher = mock.patch("caregivers.forms.geocode", return_value=WASHINGTON_SQUARE)
        self.geocode = patcher.start()
        self.addCleanup(patcher.stop)
        self.user = get_user_model().objects.create_user("cg", password="pw-12345!")
        self.client.force_login(self.user)

    def post_profile(self, **overrides):
        data = {
            "first_name": "Chloe",
            "last_name": "Shih",
            "years_of_experience": 2,
            "address": "70 Washington Square South",
            "service_radius_miles": 4,
            "accepting_new_bookings": "on",
        }
        data.update(overrides)
        return self.client.post(reverse("create_caregiver_profile"), data, follow=True)

    def test_create_form_shows_address_and_radius_fields(self):
        response = self.client.get(reverse("create_caregiver_profile"))
        self.assertContains(response, 'name="address"')
        self.assertContains(response, 'name="service_radius_miles"')

    def test_create_saves_location(self):
        self.post_profile()
        caregiver = CaregiverProfile.objects.get(user=self.user)
        self.assertEqual(caregiver.latitude, Decimal("40.729"))
        self.assertEqual(caregiver.service_radius_miles, 4)

    def test_public_profile_never_shows_the_address(self):
        response = self.post_profile()
        self.assertNotContains(response, "70 Washington Square South")

    def test_outage_shows_a_warning(self):
        self.geocode.side_effect = GeocodingUnavailable("down")
        response = self.post_profile()
        self.assertContains(response, "couldn&#x27;t look up your address")
        self.assertTrue(CaregiverProfile.objects.filter(user=self.user).exists())

    def test_edit_with_outage_shows_a_warning(self):
        self.post_profile()
        caregiver = CaregiverProfile.objects.get(user=self.user)
        self.geocode.side_effect = GeocodingUnavailable("down")
        data = {
            "first_name": "Chloe",
            "last_name": "Shih",
            "years_of_experience": 2,
            "address": "7th Ave and 9th St, Brooklyn",
            "service_radius_miles": 4,
        }
        response = self.client.post(
            reverse("edit_caregiver_profile", args=[caregiver.pk]), data, follow=True
        )
        self.assertContains(response, "couldn&#x27;t look up your address")


class GeocodeCaregiversCommandTests(TestCase):
    def run_command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("caregivers.management.commands.geocode_caregivers.time.sleep"):
            call_command("geocode_caregivers", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def make(self, **fields):
        defaults = {"name": "Chloe", "service_area": "Village", "address": "70 Washington Sq S"}
        defaults.update(fields)
        return CaregiverProfile.objects.create(**defaults)

    @mock.patch("caregivers.management.commands.geocode_caregivers.geocode")
    def test_fills_in_missing_coordinates_only(self, geocode_mock):
        geocode_mock.return_value = WASHINGTON_SQUARE
        missing = self.make()
        done = self.make(latitude=Decimal("40.661"), longitude=Decimal("-73.989"))
        no_address = self.make(address="")
        out, _ = self.run_command()
        geocode_mock.assert_called_once_with("70 Washington Sq S")
        missing.refresh_from_db()
        done.refresh_from_db()
        no_address.refresh_from_db()
        self.assertEqual(missing.latitude, Decimal("40.729"))
        self.assertEqual(done.latitude, Decimal("40.661"))
        self.assertIsNone(no_address.latitude)
        self.assertIn("Updated 1, not found 0", out)

    @mock.patch("caregivers.management.commands.geocode_caregivers.geocode")
    def test_all_option_refreshes_everyone_with_an_address(self, geocode_mock):
        geocode_mock.return_value = WASHINGTON_SQUARE
        self.make(latitude=Decimal("40.661"), longitude=Decimal("-73.989"))
        self.make()
        out, _ = self.run_command("--all")
        self.assertEqual(geocode_mock.call_count, 2)
        self.assertIn("Updated 2", out)

    @mock.patch("caregivers.management.commands.geocode_caregivers.geocode")
    def test_reports_addresses_not_found(self, geocode_mock):
        geocode_mock.return_value = None
        self.make()
        out, _ = self.run_command()
        self.assertIn("Updated 0, not found 1", out)

    @mock.patch(
        "caregivers.management.commands.geocode_caregivers.geocode",
        side_effect=GeocodingUnavailable("down"),
    )
    def test_stops_when_service_is_down(self, geocode_mock):
        self.make()
        self.make()
        _, err = self.run_command()
        self.assertEqual(geocode_mock.call_count, 1)
        self.assertIn("unavailable", err)


class HouseNumberGuardTests(SimpleTestCase):
    """GeoSearch returns its closest guess even for wrong addresses."""

    @mock.patch("caregivers.geocoding.urlopen")
    def test_wrong_house_number_is_treated_as_not_found(self, urlopen):
        hit = feature(-74.15, 40.626, "Mariners Harbor", "Staten Island")
        hit["properties"]["label"] = "45 HUDSON PLACE, Staten Island, NY, USA"
        urlopen.return_value = geosearch_response([hit])
        self.assertIsNone(geocode("1 Hudson Pl, Hoboken"))

    @mock.patch("caregivers.geocoding.urlopen")
    def test_queens_style_house_number_matches(self, urlopen):
        hit = feature(-73.936, 40.742, "Long Island City", "Queens")
        hit["properties"]["label"] = "31-00 47 AVENUE, Long Island City, NY, USA"
        urlopen.return_value = geosearch_response([hit])
        location = geocode("31-00 47th Ave, Queens")
        self.assertEqual(location.neighborhood, "Long Island City")
        self.assertEqual(location.label, "31-00 47 AVENUE, Long Island City, NY, USA")

    @mock.patch("caregivers.geocoding.urlopen")
    def test_place_name_without_number_is_accepted(self, urlopen):
        hit = feature(-73.9857, 40.7484, "Midtown", "Manhattan")
        hit["properties"]["label"] = "EMPIRE STATE BUILDING, New York, NY, USA"
        urlopen.return_value = geosearch_response([hit])
        self.assertIsNotNone(geocode("Empire State Building"))


class LocationConfirmationTests(TestCase):
    @mock.patch("caregivers.forms.geocode")
    def test_profile_shows_the_neighborhood_without_a_placement_message(self, geocode_mock):
        geocode_mock.return_value = Location(
            latitude=Decimal("40.729"), longitude=Decimal("-73.997"),
            neighborhood="Greenwich Village", borough="Manhattan",
            label="70 WASHINGTON SQUARE SOUTH, New York, NY, USA",
        )
        user = get_user_model().objects.create_user("cg2", password="pw-12345!")
        self.client.force_login(user)
        response = self.client.post(
            reverse("create_caregiver_profile"),
            {
                "first_name": "Chloe", "last_name": "Shih", "years_of_experience": 1,
                "address": "70 Washington Square South", "service_radius_miles": 3,
            },
            follow=True,
        )
        self.assertNotContains(response, "We placed you at")
        self.assertContains(response, "Greenwich Village, Manhattan")
