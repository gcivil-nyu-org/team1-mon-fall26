"""Off-leash areas from NYC Parks' dog areas directory (NYC Open Data
ipbu-mtcs), placed with Parks Properties (enfh-gkve). Downloads are mocked;
rows look like the real ones."""

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

from places.management.commands.import_off_leash_areas import update_off_leash_areas
from places.models import Place
from places.nyc_open_data import OpenDataUnavailable
from places.off_leash import (
    DEFAULT_HOURS,
    EARLY_HOURS,
    middle,
    off_leash_areas,
    properties_url,
)

EXPLORE = reverse("places:explore")


def square(lng, lat, size=0.004):
    return {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [lng, lat],
                    [lng + size, lat],
                    [lng + size, lat + size],
                    [lng, lat + size],
                    [lng, lat],
                ]
            ]
        ],
    }


def entry(**fields):
    data = {
        "Prop_ID": "B080",
        "Name": "Asser Levy Park Off-Leash Area",
        "Address": "Surf Avenue and West 5th Street",
        "DogRuns_Type": "Off-Leash",
        "Accessible": "N",
        "Notes": None,
    }
    data.update(fields)
    return data


def park(prop_id="B080", name="Asser Levy Park", lng=-73.973, lat=40.574, **fields):
    data = {
        "gispropnum": prop_id,
        "signname": name,
        "zipcode": "11224",
        "multipolygon": square(lng, lat),
    }
    data.update(fields)
    return data


class ParseTests(SimpleTestCase):
    def test_an_off_leash_area(self):
        [place] = off_leash_areas([entry()], [park()])
        self.assertEqual(place["name"], "Asser Levy Park Off-Leash Area")
        self.assertEqual(place["source_id"], "B080-asser-levy-park-off-leash-area")
        self.assertEqual(place["address"], "Surf Avenue and West 5th Street")
        self.assertEqual(place["neighborhood"], "Asser Levy Park")
        self.assertEqual(place["borough"], "Brooklyn")
        self.assertEqual(place["zip_code"], "11224")
        self.assertEqual(place["latitude"], Decimal("40.576000"))
        self.assertEqual(place["longitude"], Decimal("-73.971000"))
        self.assertEqual(place["hours"], DEFAULT_HOURS)
        self.assertEqual(place["features"], "")

    def test_dog_runs_and_unknown_types_are_left_out(self):
        rows = [entry(DogRuns_Type="Run"), entry(DogRuns_Type=None)]
        self.assertEqual(off_leash_areas(rows, [park()]), [])

    def test_parks_that_cant_be_placed_are_left_out(self):
        self.assertEqual(off_leash_areas([entry(Prop_ID="Q999")], [park()]), [])
        no_shape = park(multipolygon=None)
        self.assertEqual(off_leash_areas([entry()], [no_shape]), [])
        far_away = park(lng=-80.0, lat=35.0)
        self.assertEqual(off_leash_areas([entry()], [far_away]), [])

    def test_early_morning_only(self):
        rows = [
            entry(Name="MacNeil Park Off-Leash Area: 6:00 a.m. - 9:00 a.m. Only"),
            entry(
                Prop_ID="Q393D",
                Name="Yellowstone Park Off-Leash Area",
                Notes="Hours: 6:00 a.m. to 9:00 a.m. only ",
            ),
        ]
        places = off_leash_areas(rows, [park(), park("Q393D", "Yellowstone Park")])
        self.assertEqual(
            [p["name"] for p in places],
            ["MacNeil Park Off-Leash Area", "Yellowstone Park Off-Leash Area"],
        )
        for place in places:
            self.assertEqual(place["hours"], EARLY_HOURS)
            self.assertEqual(place["features"], "")

    def test_directions_and_notes_become_features(self):
        [place] = off_leash_areas(
            [
                entry(
                    Name="Crotona  Park   Off-Leash Area",
                    Address="Except for playgrounds, all areas of the park are "
                    "off-leash during designated hours.",
                    Notes="Off-leash dogs welcome on the Great Lawn.<br>"
                    '<a href="http://nycgovparks.org/map.pdf">Please download our '
                    "map.</a> Please see the signs.",
                )
            ],
            [park()],
        )
        self.assertEqual(place["name"], "Crotona Park Off-Leash Area")
        self.assertEqual(place["address"], "")
        self.assertEqual(
            place["features"].splitlines(),
            [
                "Except for playgrounds, all areas of the park are off-leash "
                "during designated hours.",
                "Off-leash dogs welcome on the Great Lawn.",
            ],
        )

    def test_long_descriptions_arent_addresses(self):
        long = "Field at the end of the trail bordered by Prospect Avenue, " * 2
        [place] = off_leash_areas([entry(Address=long)], [park()])
        self.assertEqual(place["address"], "")
        self.assertIn("Field at the end of the trail", place["features"])

    def test_the_same_area_listed_twice_keeps_two_ids(self):
        places = off_leash_areas([entry(), entry()], [park()])
        self.assertEqual(
            [p["source_id"] for p in places],
            [
                "B080-asser-levy-park-off-leash-area",
                "B080-asser-levy-park-off-leash-area-2",
            ],
        )

    def test_boroughs_from_the_park_id(self):
        ids = {
            "X004": "Bronx",
            "M010": "Manhattan",
            "Q099": "Queens",
            "R005": "Staten Island",
        }
        rows = [entry(Prop_ID=i, Name=f"Area {i}") for i in ids]
        places = off_leash_areas(rows, [park(i) for i in ids])
        self.assertEqual({p["name"][5:]: p["borough"] for p in places}, ids)

    def test_first_zip_code_of_a_big_park(self):
        [place] = off_leash_areas([entry()], [park(zipcode="10460, 10466, 10467")])
        self.assertEqual(place["zip_code"], "10460")

    def test_properties_url_asks_for_these_parks_only(self):
        url = properties_url({"X004", "B080"})
        self.assertIn("enfh-gkve.json?", url)
        self.assertIn("gispropnum+in+%28%27B080%27%2C%27X004%27%29", url)


class MiddleTests(SimpleTestCase):
    def test_centroid_of_the_largest_piece(self):
        shape = square(-73.97, 40.57)
        shape["coordinates"].append(square(-73.90, 40.60, size=0.001)["coordinates"][0])
        self.assertEqual(middle(shape), (Decimal("40.572000"), Decimal("-73.968000")))

    def test_a_point_inside_an_l_shaped_park(self):
        # An L whose centroid falls in the missing corner.
        l_shape = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0, 0], [10, 0], [10, 1], [1, 1], [1, 10], [0, 10], [0, 0]]]
            ],
        }
        lat, lng = middle(l_shape)
        self.assertTrue(0 <= float(lng) <= 1 or float(lat) <= 1)

    def test_nothing_to_place(self):
        self.assertIsNone(middle(None))
        self.assertIsNone(middle({"type": "MultiPolygon", "coordinates": []}))


class UpdateTests(TestCase):
    def setUp(self):
        # Start without the dog runs the data migration adds.
        Place.objects.all().delete()

    def rows(self, **changes):
        place = off_leash_areas([entry()], [park()])[0]
        place.update(changes)
        return [place]

    def test_adds_then_updates(self):
        self.assertEqual(
            update_off_leash_areas(self.rows(), date(2026, 11, 16)), (1, 0, 0)
        )
        place = Place.objects.get(source=Place.Source.NYC_PARKS_DOG_AREAS)
        self.assertEqual(place.category, Place.Category.OFF_LEASH)
        self.assertEqual(place.checked_on, date(2026, 11, 16))
        self.assertEqual(
            place.source_url(), "https://data.cityofnewyork.us/d/ipbu-mtcs"
        )
        result = update_off_leash_areas(
            self.rows(address="Surf Ave"), date(2026, 11, 17)
        )
        self.assertEqual(result, (0, 1, 0))
        place.refresh_from_db()
        self.assertEqual(place.address, "Surf Ave")

    def test_areas_no_longer_listed_are_hidden_and_come_back(self):
        update_off_leash_areas(self.rows(), date(2026, 11, 16))
        self.assertEqual(update_off_leash_areas([], date(2026, 11, 17)), (0, 0, 1))
        self.assertFalse(Place.objects.get().is_active)
        update_off_leash_areas(self.rows(), date(2026, 11, 18))
        self.assertTrue(Place.objects.get().is_active)

    def test_admin_edits_are_kept(self):
        update_off_leash_areas(self.rows(), date(2026, 11, 16))
        Place.objects.update(name="Asser Levy dog area", edited_at=timezone.now())
        self.assertEqual(
            update_off_leash_areas(self.rows(), date(2026, 11, 17)), (0, 0, 0)
        )
        self.assertEqual(update_off_leash_areas([], date(2026, 11, 18)), (0, 0, 0))
        place = Place.objects.get()
        self.assertEqual(place.name, "Asser Levy dog area")
        self.assertTrue(place.is_active)

    def test_other_places_arent_touched(self):
        Place.objects.create(
            name="Maple Dog Run",
            category=Place.Category.DOG_PARK,
            source=Place.Source.NYC_PARKS,
            source_id="B001",
            latitude=Decimal("40.67"),
            longitude=Decimal("-73.97"),
        )
        before = Place.objects.count()
        update_off_leash_areas([], date(2026, 11, 16))
        self.assertTrue(Place.objects.get(source_id="B001").is_active)
        self.assertEqual(Place.objects.count(), before)


class CommandTests(TestCase):
    def setUp(self):
        Place.objects.all().delete()

    def files(self, directory, properties):
        paths = []
        for data in (directory, properties):
            f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(data, f)
            f.close()
            paths.append(f.name)
        return paths

    def test_import_from_files(self):
        directory, properties = self.files(
            [entry(), entry(DogRuns_Type="Run")], [park()]
        )
        out = io.StringIO()
        call_command(
            "import_off_leash_areas",
            directory=directory,
            properties=properties,
            stdout=out,
        )
        self.assertIn(
            "1 off-leash areas from NYC Parks: 1 added, 0 updated", out.getvalue()
        )
        self.assertEqual(Place.objects.filter(category="off_leash").count(), 1)

    @mock.patch("places.management.commands.import_off_leash_areas.download")
    def test_downloads_the_directory_then_the_parks(self, download):
        download.side_effect = [[entry()], [park()]]
        call_command("import_off_leash_areas", stdout=io.StringIO())
        self.assertEqual(download.call_count, 2)
        self.assertIn("nycgovparks.org", download.call_args_list[0].args[0])
        self.assertIn("B080", download.call_args_list[1].args[0])
        self.assertEqual(Place.objects.count(), 1)

    @mock.patch(
        "places.management.commands.import_off_leash_areas.download",
        side_effect=OpenDataUnavailable("timed out"),
    )
    def test_unreachable(self, download):
        with self.assertRaisesMessage(CommandError, "Couldn't reach NYC Parks"):
            call_command("import_off_leash_areas", stdout=io.StringIO())

    @mock.patch("places.management.commands.import_off_leash_areas.download")
    def test_unexpected_data_changes_nothing(self, download):
        for side_effect, message in (
            ([{"error": "x"}], "NYC Parks sent something unexpected."),
            ([[entry(DogRuns_Type="Run")]], "No off-leash areas found"),
            ([[entry()], {"error": "x"}], "NYC Open Data sent something unexpected."),
            ([[entry()], []], "No off-leash areas could be placed"),
        ):
            download.side_effect = side_effect
            with self.assertRaisesMessage(CommandError, message):
                call_command("import_off_leash_areas", stdout=io.StringIO())
        self.assertFalse(Place.objects.exists())


class ExploreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()
        cls.user = get_user_model().objects.create_user("kat")
        update_off_leash_areas(off_leash_areas([entry()], [park()]), date(2026, 11, 16))

    def setUp(self):
        self.client.force_login(self.user)

    def test_off_leash_chip_and_details(self):
        response = self.client.get(EXPLORE)
        self.assertContains(response, ">Off-leash areas</a>")
        self.assertContains(response, "Asser Levy Park Off-Leash Area")
        self.assertContains(response, '<span class="place-badge">Off-leash</span>')
        self.assertContains(response, DEFAULT_HOURS)
        self.assertContains(
            response,
            "Outside these hours, dogs must be on a leash no longer than 6 feet.",
        )

    def test_only_off_leash_areas(self):
        Place.objects.create(
            name="Bark & Brew Café",
            category=Place.Category.CAFE,
            latitude=Decimal("40.575"),
            longitude=Decimal("-73.972"),
        )
        response = self.client.get(EXPLORE, {"category": "off_leash"})
        self.assertContains(response, "Asser Levy Park Off-Leash Area")
        self.assertNotContains(response, "Bark &amp; Brew Café")
        self.assertContains(response, "1 off-leash area")
