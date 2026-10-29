"""Tests for the profile form's address suggestions and neighborhood auto-fill.
GeoSearch is always mocked."""

from unittest import mock
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..geocoding import GeocodingUnavailable, Suggestion, autocomplete
from .test_geocoding import WASHINGTON_SQUARE, feature, geosearch_response


class AutocompleteTests(SimpleTestCase):
    @mock.patch("caregivers.geocoding.urlopen")
    def test_returns_tidy_addresses_with_their_neighborhood(self, urlopen):
        urlopen.return_value = geosearch_response([feature(-73.997, 40.729)])
        self.assertEqual(
            autocomplete("70 washington sq"),
            [
                Suggestion(
                    "70 Washington Square South, Manhattan",
                    "Greenwich Village",
                    "Manhattan",
                )
            ],
        )

    @mock.patch("caregivers.geocoding.urlopen")
    def test_short_text_is_not_looked_up(self, urlopen):
        self.assertEqual(autocomplete("70"), [])
        urlopen.assert_not_called()

    @mock.patch("caregivers.geocoding.urlopen", side_effect=URLError("down"))
    def test_outage_raises(self, urlopen):
        with self.assertRaises(GeocodingUnavailable):
            autocomplete("70 washington sq")


class AddressLookupViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            "sitter", password="Pawpal!2026x"
        )

    def setUp(self):
        self.client.force_login(self.user)

    @mock.patch(
        "caregivers.views.autocomplete",
        return_value=[
            Suggestion(
                "70 Washington Square South, Manhattan",
                "Greenwich Village",
                "Manhattan",
            )
        ],
    )
    def test_suggestions(self, autocomplete):
        response = self.client.get(
            reverse("address_suggestions"), {"q": "70 washington"}
        )
        self.assertEqual(
            response.json(),
            {
                "suggestions": [
                    {
                        "address": "70 Washington Square South, Manhattan",
                        "neighborhood": "Greenwich Village, Manhattan",
                    }
                ]
            },
        )
        autocomplete.assert_called_once_with("70 washington")

    @mock.patch(
        "caregivers.views.autocomplete", side_effect=GeocodingUnavailable("down")
    )
    def test_suggestions_when_service_is_down(self, autocomplete):
        response = self.client.get(
            reverse("address_suggestions"), {"q": "70 washington"}
        )
        self.assertEqual(response.json(), {"suggestions": []})

    @mock.patch("caregivers.views.geocode", return_value=WASHINGTON_SQUARE)
    def test_neighborhood(self, geocode):
        response = self.client.get(
            reverse("address_neighborhood"), {"address": "70 Washington Square South"}
        )
        self.assertEqual(
            response.json(), {"neighborhood": "Greenwich Village, Manhattan"}
        )

    @mock.patch("caregivers.views.geocode", return_value=None)
    def test_unknown_address_has_no_neighborhood(self, geocode):
        response = self.client.get(
            reverse("address_neighborhood"), {"address": "nowhere"}
        )
        self.assertEqual(response.json(), {"neighborhood": ""})

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(
            reverse("address_suggestions"), {"q": "70 washington"}
        )
        self.assertEqual(response.status_code, 302)
