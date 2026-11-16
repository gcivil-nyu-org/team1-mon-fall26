"""Dog fountains from NYC Parks' Drinking Fountains on NYC Open Data
(qnv7-p7a2). Downloads are mocked; rows look like the API's."""

import io
import json
import tempfile
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from places.dog_fountains import API_URL, FEATURE, dog_fountains
from places.management.commands.import_dog_fountains import update_dog_fountains
from places.models import Place
from places.nyc_open_data import OpenDataUnavailable

EXPLORE = reverse("places:explore")


def row(**fields):
    """One fountain as the API returns it (a real Central Park row)."""
    data = {
        "system": "M010-DF0594",
        "fountainty": "E and Dog",
        "position": "Under Tree, In Shade",
        "painted": "YES",
        "gispropnum": "M010",
        "propertyna": "Central Park",
        "borough": "M",
        "fountainco": "2",
        "decription": "E and Dog-Central Park-Cedar Hill",
        "featuresta": "Active",
        "the_geom": {"type": "Point", "coordinates": [-73.965477, 40.775604]},
    }
    data.update(fields)
    return data


class ParseTests(SimpleTestCase):
    def test_a_dog_fountain(self):
        [place] = dog_fountains([row()])
        self.assertEqual(
            place,
            {
                "source_id": "M010-DF0594",
                "name": "Dog fountain, Central Park (Cedar Hill)",
                "neighborhood": "Central Park",
                "borough": "Manhattan",
                "latitude": Decimal("40.775604"),
                "longitude": Decimal("-73.965477"),
                "features": f"{FEATURE}\nUnder tree, in shade",
            },
        )

    def test_only_working_fountains_with_a_dog_bowl(self):
        rows = [
            row(fountainty="E", system="A"),
            row(featuresta="Inactive", system="B"),
            row(fountainty="Dog Fountain", system="C"),
            row(fountainty="F High Low and Dog", system="D"),
        ]
        self.assertEqual([p["source_id"] for p in dog_fountains(rows)], ["C", "D"])

    def test_fountains_in_playgrounds_are_left_out(self):
        rows = [
            row(position="In Playground", system="A"),
            row(position="Under Tree, In Playground", system="B"),
            row(position="Just Outside Playground", system="C"),
        ]
        self.assertEqual([p["source_id"] for p in dog_fountains(rows)], ["C"])

    def test_missing_or_bad_points(self):
        rows = [
            row(the_geom=None, system="A"),
            row(the_geom={"type": "Point", "coordinates": ["x", "y"]}, system="B"),
            row(the_geom={"type": "Point", "coordinates": [-80.0, 35.0]}, system="C"),
            row(system=""),
        ]
        self.assertEqual(dog_fountains(rows), [])

    def test_names_without_an_area(self):
        rows = [
            row(decription="E and Dog-Adam Yauch Park", propertyna="Adam Yauch Park"),
            row(
                system="X",
                propertyna="Hudson River Park",
                decription="F-Hudson River Park-Hudson River Park",
            ),
            row(system="Y", propertyna="", decription=""),
        ]
        names = sorted(p["name"] for p in dog_fountains(rows))
        self.assertEqual(
            names,
            [
                "Dog fountain",
                "Dog fountain, Adam Yauch Park",
                "Dog fountain, Hudson River Park",
            ],
        )

    def test_no_position(self):
        [place] = dog_fountains([row(position=None)])
        self.assertEqual(place["features"], FEATURE)

    def test_the_api_asks_for_dog_fountains(self):
        self.assertIn("qnv7-p7a2.json?", API_URL)
        self.assertIn("Dog", API_URL)


class UpdateTests(TestCase):
    def setUp(self):
        Place.objects.all().delete()

    def test_adds_updates_and_hides(self):
        rows = dog_fountains([row()])
        self.assertEqual(update_dog_fountains(rows, date(2026, 11, 16)), (1, 0, 0))
        place = Place.objects.get()
        self.assertEqual(place.category, Place.Category.DOG_FOUNTAIN)
        self.assertEqual(
            place.source_url(), "https://data.cityofnewyork.us/d/qnv7-p7a2"
        )
        moved = dog_fountains([row(position="Out in Open")])
        self.assertEqual(update_dog_fountains(moved, date(2026, 11, 17)), (0, 1, 0))
        place.refresh_from_db()
        self.assertIn("Out in open", place.features)
        self.assertEqual(update_dog_fountains([], date(2026, 11, 18)), (0, 0, 1))
        place.refresh_from_db()
        self.assertFalse(place.is_active)

    def test_admin_edits_are_kept(self):
        update_dog_fountains(dog_fountains([row()]), date(2026, 11, 16))
        Place.objects.update(name="Cedar Hill fountain", edited_at=timezone.now())
        update_dog_fountains(dog_fountains([row()]), date(2026, 11, 17))
        update_dog_fountains([], date(2026, 11, 18))
        place = Place.objects.get()
        self.assertEqual(place.name, "Cedar Hill fountain")
        self.assertTrue(place.is_active)


class CommandTests(TestCase):
    def setUp(self):
        Place.objects.all().delete()

    def test_import_from_a_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([row(), row(fountainty="E", system="Z")], f)
        out = io.StringIO()
        call_command("import_dog_fountains", file=f.name, stdout=out)
        self.assertIn("1 dog fountains from NYC Parks: 1 added", out.getvalue())

    @mock.patch(
        "places.management.commands.import_dog_fountains.download",
        return_value=[row()],
    )
    def test_downloads(self, download):
        call_command("import_dog_fountains", stdout=io.StringIO())
        download.assert_called_once_with(API_URL)
        self.assertEqual(Place.objects.count(), 1)

    @mock.patch("places.management.commands.import_dog_fountains.download")
    def test_problems_change_nothing(self, download):
        for side_effect, message in (
            (OpenDataUnavailable("timed out"), "Couldn't reach NYC Open Data"),
            ([{"error": "x"}], None),
            ([[row(fountainty="E")]], "No dog fountains found"),
        ):
            download.side_effect = (
                side_effect if isinstance(side_effect, Exception) else None
            )
            if not isinstance(side_effect, Exception):
                download.return_value = side_effect[0]
            with self.assertRaises(CommandError) as raised:
                call_command("import_dog_fountains", stdout=io.StringIO())
            if message:
                self.assertIn(message, str(raised.exception))
        self.assertFalse(Place.objects.exists())


class ExploreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()
        cls.user = get_user_model().objects.create_user("kat")
        update_dog_fountains(dog_fountains([row()]), date(2026, 11, 16))

    def setUp(self):
        self.client.force_login(self.user)

    def test_dog_fountains_chip_and_details(self):
        response = self.client.get(EXPLORE, {"category": "dog_fountain"})
        self.assertContains(response, ">Dog fountains</a>")
        self.assertContains(response, "Dog fountain, Central Park (Cedar Hill)")
        self.assertContains(response, '<span class="place-badge">Dog fountain</span>')
        self.assertContains(response, FEATURE)
        self.assertContains(response, "1 dog fountain")
