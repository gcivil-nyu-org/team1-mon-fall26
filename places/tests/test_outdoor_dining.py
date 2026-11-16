"""Outdoor dining from NYC DOT's Dining Out NYC licenses on NYC Open Data
(fpeh-f7ci). Downloads are mocked; rows look like the API's."""

import io
import json
import tempfile
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from places.dining_out import outdoor_dining, tidy
from places.management.commands.import_outdoor_dining import update_outdoor_dining
from places.models import Place
from places.nyc_open_data import OpenDataUnavailable
from places.search import MAX_OUTDOOR_DINING

EXPLORE = reverse("places:explore")


def row(**fields):
    """One license as the API returns it (the first row of the real data)."""
    data = {
        "business_legal_name": "BROOKLYN BURGERS LLC",
        "assumed_name_s": "BURGERFI",
        "street": "719 86 STREET",
        "city": "BROOKLYN",
        "borough": "Brooklyn",
        "postcode": "11228",
        "license_type": "Sidewalk",
        "license_status": "Issued",
        "latitude": "40.618574604774",
        "longitude": "-74.021381725269",
    }
    data.update(fields)
    return {key: value for key, value in data.items() if value is not None}


class RowsTests(SimpleTestCase):
    def test_tidy(self):
        self.assertEqual(tidy("BURGERFI"), "Burgerfi")
        self.assertEqual(tidy("719  86 STREET"), "719 86 Street")
        self.assertEqual(tidy("Café Mogador"), "Café Mogador")
        self.assertEqual(tidy(None), "")

    def test_a_license_becomes_a_place(self):
        [place] = outdoor_dining([row()])
        self.assertEqual(place["name"], "Burgerfi")
        self.assertEqual(place["address"], "719 86 Street")
        self.assertEqual(place["borough"], "Brooklyn")
        self.assertEqual(place["zip_code"], "11228")
        self.assertEqual(place["latitude"], Decimal("40.618575"))
        self.assertEqual(place["longitude"], Decimal("-74.021382"))
        self.assertEqual(place["features"], "Sidewalk seating")
        self.assertEqual(len(place["source_id"]), 16)
        # The same business gets the same id on the next import.
        self.assertEqual(outdoor_dining([row()])[0]["source_id"], place["source_id"])

    def test_sidewalk_and_roadway_are_one_place(self):
        [place] = outdoor_dining([row(), row(license_type="Roadway")])
        self.assertEqual(place["features"], "Roadway seating\nSidewalk seating")

    def test_legal_name_when_there_is_no_trade_name(self):
        [place] = outdoor_dining([row(assumed_name_s="")])
        self.assertEqual(place["name"], "Brooklyn Burgers Llc")

    def test_rows_that_are_left_out(self):
        rows = [
            # Jersey City: no borough (in the real data).
            row(city="JERSEY CITY", borough=None, latitude="40.742486"),
            row(license_status="Expired"),
            row(latitude=None),
            row(longitude="not a number"),
            row(assumed_name_s="", business_legal_name=""),
            row(latitude="39.9"),  # outside New York City
        ]
        self.assertEqual(outdoor_dining(rows), [])

    def test_the_bronx(self):
        [place] = outdoor_dining([row(borough="THE BRONX")])
        self.assertEqual(place["borough"], "Bronx")

    def test_no_license_type(self):
        [place] = outdoor_dining([row(license_type="")])
        self.assertEqual(place["features"], "Outdoor seating")


class UpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()

    def test_adds_updates_and_hides(self):
        today = timezone.localdate()
        gone = Place.objects.create(
            name="Closed Bistro",
            category=Place.Category.OUTDOOR_DINING,
            source=Place.Source.DINING_OUT,
            source_id="gone",
            latitude=40.7,
            longitude=-73.9,
        )
        cafe = Place.objects.create(
            name="Bark & Brew Café", category="cafe", latitude=40.67, longitude=-73.98
        )
        self.assertEqual(
            update_outdoor_dining(outdoor_dining([row()]), today), (1, 0, 1)
        )
        place = Place.objects.get(source=Place.Source.DINING_OUT, is_active=True)
        self.assertEqual(place.category, Place.Category.OUTDOOR_DINING)
        self.assertEqual(place.checked_on, today)
        gone.refresh_from_db()
        cafe.refresh_from_db()
        self.assertFalse(gone.is_active)
        self.assertTrue(cafe.is_active)  # the team's places are left alone

        # Licensed again after being hidden: shown again, with its new seating.
        place.is_active = False
        place.save()
        rows = outdoor_dining([row(), row(license_type="Roadway")])
        self.assertEqual(update_outdoor_dining(rows, today), (0, 1, 0))
        place.refresh_from_db()
        self.assertTrue(place.is_active)
        self.assertIn("Roadway seating", place.features)

    def test_admin_edits_are_kept(self):
        [data] = outdoor_dining([row()])
        place = Place.objects.create(
            name="Fixed by an admin",
            category=Place.Category.OUTDOOR_DINING,
            source=Place.Source.DINING_OUT,
            source_id=data["source_id"],
            latitude=40.6,
            longitude=-74.0,
            edited_at=timezone.now(),
        )
        self.assertEqual(update_outdoor_dining([data], timezone.localdate()), (0, 0, 0))
        place.refresh_from_db()
        self.assertEqual(place.name, "Fixed by an admin")


class CommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()

    def run_command(self, **options):
        out = io.StringIO()
        call_command("import_outdoor_dining", stdout=out, **options)
        return out.getvalue()

    @mock.patch("places.management.commands.import_outdoor_dining.download")
    def test_downloads_from_the_api(self, download):
        download.return_value = [row(), row(license_type="Roadway")]
        out = self.run_command()
        self.assertIn(
            "1 places with outdoor dining from NYC Open Data: "
            "1 added, 0 updated, 0 no longer licensed",
            out,
        )
        url = download.call_args.args[0]
        self.assertIn("fpeh-f7ci.json", url)
        self.assertIn("license_status=Issued", url)

    def test_reads_a_saved_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump([row()], f)
            f.flush()
            self.run_command(file=f.name)
        self.assertEqual(Place.objects.filter(source="dining_out").count(), 1)

    @mock.patch(
        "places.management.commands.import_outdoor_dining.download",
        side_effect=OpenDataUnavailable("down"),
    )
    def test_nothing_changes_when_unreachable(self, download):
        with self.assertRaisesMessage(CommandError, "Couldn't reach NYC Open Data"):
            self.run_command()

    @mock.patch("places.management.commands.import_outdoor_dining.download")
    def test_nothing_changes_without_data(self, download):
        download.return_value = {"error": "bad"}
        with self.assertRaisesMessage(CommandError, "something unexpected"):
            self.run_command()
        download.return_value = [row(license_status="Expired")]
        with self.assertRaisesMessage(CommandError, "No outdoor dining found"):
            self.run_command()


class ExploreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()
        cls.owner = get_user_model().objects.create_user("kat", password="pw-12345!")
        cls.park = Place.objects.create(
            name="Washington Park Dog Run",
            category="dog_park",
            latitude="40.6730",
            longitude="-73.9860",
            borough="Brooklyn",
        )
        cls.dining = Place.objects.create(
            name="Burgerfi",
            category=Place.Category.OUTDOOR_DINING,
            source=Place.Source.DINING_OUT,
            source_id="abc",
            address="719 86 Street",
            borough="Brooklyn",
            latitude="40.6720",
            longitude="-73.9790",
            features="Sidewalk seating",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_all_leaves_out_outdoor_dining(self):
        response = self.client.get(EXPLORE, {"location": "Park Slope"})
        self.assertEqual(response.context["places"], [self.park])
        self.assertContains(response, "Outdoor dining</a>")

    def test_outdoor_dining_needs_an_area(self):
        response = self.client.get(EXPLORE, {"category": "outdoor_dining"})
        self.assertEqual(response.context["places"], [])
        self.assertContains(response, "Search an area to see outdoor dining")

    def test_outdoor_dining_near_an_area(self):
        response = self.client.get(
            EXPLORE, {"category": "outdoor_dining", "location": "Park Slope"}
        )
        self.assertEqual(response.context["places"], [self.dining])
        self.assertContains(response, "1 outdoor dining spot")
        self.assertContains(response, "Sidewalk seating")
        self.assertContains(
            response, "Dogs are allowed only if the restaurant says yes"
        )
        self.assertContains(response, "https://data.cityofnewyork.us/d/fpeh-f7ci")

    def test_at_most_the_nearest_ones(self):
        Place.objects.bulk_create(
            Place(
                name=f"Spot {n}",
                category=Place.Category.OUTDOOR_DINING,
                latitude=Decimal("40.6720") + Decimal(n) / 100000,
                longitude="-73.9790",
            )
            for n in range(MAX_OUTDOOR_DINING + 5)
        )
        response = self.client.get(
            EXPLORE, {"category": "outdoor_dining", "location": "Park Slope"}
        )
        self.assertEqual(len(response.context["places"]), MAX_OUTDOOR_DINING)

    def test_admins_can_pick_outdoor_dining(self):
        admin = get_user_model().objects.create_user("ada", is_staff=True)
        self.client.force_login(admin)
        response = self.client.get(reverse("places:manage_edit", args=[self.dining.pk]))
        self.assertContains(response, ">Outdoor dining</span>")
        self.assertEqual(
            self.dining.source_url(), "https://data.cityofnewyork.us/d/fpeh-f7ci"
        )
        self.assertEqual(self.park.source_url(), "")
