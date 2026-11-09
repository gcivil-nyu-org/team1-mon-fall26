"""Use Reliable Location Data: dog parks come from NYC Parks' Dog Runs dataset
on NYC Open Data. NYC Open Data is never contacted; downloads are mocked."""

import io
import json
import tempfile
from datetime import date
from unittest import mock
from urllib.error import URLError

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from places.management.commands.import_dog_runs import update_dog_parks
from places.models import Place
from places.nyc_open_data import (
    DIRECTORY_URL,
    OpenDataUnavailable,
    center_of,
    dog_runs,
    download,
)

# A tiny square in Park Slope, like the dataset's run outlines.
SQUARE = [
    [-73.9862, 40.6728],
    [-73.9858, 40.6728],
    [-73.9858, 40.6732],
    [-73.9862, 40.6732],
    [-73.9862, 40.6728],
]


def feature(geometry=None, **properties):
    """One row as the dataset's GeoJSON has it (same field names)."""
    row = {
        "name": "Washington Park Dog Run",
        "system": "B163-DOGAREA0001",
        "objectid": "4001",
        "borough": "B",
        "zipcode": "11215",
        "featurestatus": "Active",
        "dog_area_type": "Dog Run",
        "surface": None,
        "seating": None,
    }
    row.update(properties)
    if geometry is None:
        geometry = {"type": "MultiPolygon", "coordinates": [[SQUARE]]}
    return {"type": "Feature", "geometry": geometry, "properties": row}


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def entry(name, address, prop_id="B111A", kind="Run"):
    """One dog run in the NYC Parks directory (same field names)."""
    return {
        "Prop_ID": prop_id,
        "Name": name,
        "Address": address,
        "DogRuns_Type": kind,
        "Accessible": "N",
        "Notes": None,
    }


WASHINGTON = entry("Washington Park Dog Run", "3rd to 4th streets, 4th to 5th avenues")


class CenterTests(SimpleTestCase):
    def test_point(self):
        point = {"type": "Point", "coordinates": [-73.98, 40.67]}
        self.assertEqual(center_of(point), (40.67, -73.98))

    def test_polygon_center(self):
        lat, lng = center_of({"type": "Polygon", "coordinates": [SQUARE]})
        self.assertAlmostEqual(lat, 40.673)
        self.assertAlmostEqual(lng, -73.986)

    def test_the_largest_of_several_polygons_is_used(self):
        tiny = [[-74.0, 40.7], [-73.99999, 40.7], [-73.99999, 40.70001], [-74.0, 40.7]]
        lat, lng = center_of(
            {"type": "MultiPolygon", "coordinates": [[tiny], [SQUARE]]}
        )
        self.assertAlmostEqual(lat, 40.673)

    def test_flat_outline_uses_the_average_point(self):
        line = [[-73.98, 40.67], [-73.98, 40.67], [-73.98, 40.67]]
        lat, lng = center_of({"type": "Polygon", "coordinates": [line]})
        self.assertAlmostEqual(lat, 40.67)

    def test_missing_or_broken_geometry(self):
        self.assertIsNone(center_of(None))
        self.assertIsNone(center_of({"type": "LineString", "coordinates": []}))
        self.assertIsNone(center_of({"type": "Polygon", "coordinates": "bad"}))


class DogRunRowsTests(SimpleTestCase):
    def test_a_row_becomes_a_place(self):
        [run] = dog_runs(collection(feature(surface="Natural", seating="Yes")))
        self.assertEqual(run["source_id"], "B163-DOGAREA0001")
        self.assertEqual(run["name"], "Washington Park Dog Run")
        self.assertEqual(run["borough"], "Brooklyn")
        self.assertEqual(run["zip_code"], "11215")
        self.assertEqual(run["neighborhood"], "Park Slope")
        self.assertAlmostEqual(run["latitude"], 40.673)
        self.assertEqual(
            run["features"],
            "Fenced off-leash dog run\nNatural surface\nSeating for people",
        )

    def test_borough_codes(self):
        for code, name in [("M", "Manhattan"), ("X", "Bronx"), ("Q", "Queens")]:
            [run] = dog_runs(collection(feature(borough=code)))
            self.assertEqual(run["borough"], name)

    def test_rows_without_a_system_id_use_the_object_id(self):
        [run] = dog_runs(collection(feature(system=None)))
        self.assertEqual(run["source_id"], "objectid-4001")

    def test_unusable_rows_are_skipped(self):
        far_away = {"type": "Point", "coordinates": [-118.24, 34.05]}
        rows = [
            feature(name=""),
            feature(featurestatus="Retired"),
            feature(geometry={"type": "LineString", "coordinates": []}),
            feature(geometry=far_away),
            feature(system=None, objectid=None),
        ]
        self.assertEqual(dog_runs(collection(*rows)), [])
        self.assertEqual(dog_runs({}), [])


class DirectoryAddressTests(SimpleTestCase):
    """Street addresses from NYC Parks' Directory of Dog Runs (ipbu-mtcs)."""

    def address(self, runs, directory, name=None):
        found = dog_runs(collection(*runs), directory)
        return {r["name"]: r["address"] for r in found}[name or found[0]["name"]]

    def test_matched_on_the_park(self):
        run = feature(gispropnum="B111A")
        self.assertEqual(
            self.address([run], [WASHINGTON]), "3rd to 4th streets, 4th to 5th avenues"
        )

    def test_without_the_directory_runs_have_no_address_field(self):
        [run] = dog_runs(collection(feature(gispropnum="B111A")))
        self.assertNotIn("address", run)

    def test_no_entry_for_the_park(self):
        run = feature(gispropnum="B999")
        self.assertEqual(self.address([run], [WASHINGTON]), "")
        self.assertEqual(self.address([feature(gispropnum=None)], [WASHINGTON]), "")

    def test_off_leash_lawns_and_vague_addresses_are_skipped(self):
        run = feature(gispropnum="B111A")
        lawn = entry("Washington Park Off-Leash Area", "The lawn", kind="Off-Leash")
        self.assertEqual(self.address([run], [lawn]), "")
        vague = entry("Washington Park Dog Run", "All areas excluding the playground")
        self.assertEqual(self.address([run], [vague]), "")
        self.assertEqual(
            self.address([run], [entry("Washington Park Dog Run", None)]), ""
        )

    def test_one_entry_for_two_runs_in_a_park(self):
        runs = [
            feature(name="Cooper Park Small Dog Run", system="A", gispropnum="B025"),
            feature(name="Cooper Park Large Dog Run", system="B", gispropnum="B025"),
            feature(name="Dyckman Rest Dog Run", system="C", gispropnum="M037"),
            feature(name="Highbridge Park Dog Run", system="D", gispropnum="M037"),
        ]
        directory = [
            entry("Cooper Park Dog Run", "Morgan Avenue and Sharon Street", "B025"),
            entry(
                "Highbridge Park Dog Run", "Amsterdam and Fort George avenues", "M037"
            ),
        ]
        found = {
            r["name"]: r["address"] for r in dog_runs(collection(*runs), directory)
        }
        self.assertEqual(
            found["Cooper Park Small Dog Run"], "Morgan Avenue and Sharon Street"
        )
        self.assertEqual(
            found["Cooper Park Large Dog Run"], "Morgan Avenue and Sharon Street"
        )
        self.assertEqual(
            found["Highbridge Park Dog Run"], "Amsterdam and Fort George avenues"
        )
        self.assertEqual(found["Dyckman Rest Dog Run"], "")  # not the Highbridge entry

    def test_several_entries_in_one_park_are_matched_by_name(self):
        runs = [
            feature(name="Dog Bone Run", system="A", gispropnum="X092"),
            feature(name="Forest Park Dog Run", system="B", gispropnum="Q015"),
        ]
        directory = [
            entry(
                "Van Cortlandt Park: Canine Court", "Broadway and 252 Street", "X092"
            ),
            entry(
                "Van Cortlandt Park: Dog Bone Run",
                "Gun Hill Road and Jerome Avenue",
                "X092",
            ),
            entry("Forest Park: K9 Korral", "Park Lane South and 85th Street", "Q015"),
            entry("Forest Park: The Barking Lot", "Park Lane", "Q015"),
        ]
        found = {
            r["name"]: r["address"] for r in dog_runs(collection(*runs), directory)
        }
        self.assertEqual(found["Dog Bone Run"], "Gun Hill Road and Jerome Avenue")
        self.assertEqual(found["Forest Park Dog Run"], "")  # can't tell which

    def test_one_entry_for_three_runs_keeps_each_runs_street(self):
        runs = [
            feature(name="105th Street Dog Run", system="A", gispropnum="M071"),
            feature(name="87th Street Dog Run", system="B", gispropnum="M071"),
        ]
        directory = [
            entry(
                "Riverside Park Dog Run (3 runs)",
                "Riverside Drive at West 72nd, West 87th, West 105th",
                "M071",
            )
        ]
        found = {
            r["name"]: r["address"] for r in dog_runs(collection(*runs), directory)
        }
        self.assertEqual(found["105th Street Dog Run"], "Riverside Drive at West 105th")
        self.assertEqual(found["87th Street Dog Run"], "Riverside Drive at West 87th")

    def test_other_streets_are_not_this_run(self):
        run = feature(name="66th Street Dog Run", gispropnum="M353")
        other = entry(
            "Riverside Park South Dog Run",
            "Hudson River Greenway at W. 72nd St",
            "M353",
        )
        self.assertEqual(self.address([run], [other]), "")

    def test_text_is_tidied(self):
        run = feature(gispropnum="B016")
        messy = entry(
            "Maria Hernandez Park Dog Run", "  Irving Ave. &amp;  Suydam St. ", "B016"
        )
        self.assertEqual(self.address([run], [messy]), "Irving Ave. & Suydam St.")


class DownloadTests(SimpleTestCase):
    @mock.patch("places.nyc_open_data.urlopen")
    def test_download(self, urlopen):
        urlopen.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(collection(feature())).encode()
        )
        self.assertEqual(len(download()["features"]), 1)
        request = urlopen.call_args.args[0]
        self.assertIn(
            "data.cityofnewyork.us/resource/hxx3-bwgv.geojson", request.full_url
        )

    @mock.patch("places.nyc_open_data.urlopen", side_effect=URLError("offline"))
    def test_unreachable(self, urlopen):
        with self.assertRaises(OpenDataUnavailable):
            download()


class SnapshotTests(TestCase):
    def test_migrate_loads_the_nyc_open_data_snapshot(self):
        parks = Place.objects.filter(source=Place.Source.NYC_PARKS)
        self.assertEqual(parks.count(), 95)
        self.assertTrue(all(p.category == Place.Category.DOG_PARK for p in parks))
        washington = parks.get(name="Washington Park Dog Run")
        self.assertEqual(washington.address, "3rd to 4th streets, 4th to 5th avenues")
        self.assertEqual(washington.neighborhood, "Park Slope")
        self.assertEqual(parks.exclude(address="").count(), 79)
        self.assertEqual(str(washington.checked_on), "2026-11-08")


class ImportCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()

    def run_command(self, geojson, directory=None):
        with tempfile.NamedTemporaryFile("w", suffix=".geojson") as f:
            json.dump(geojson, f)
            f.flush()
            options = {"file": f.name}
            with tempfile.NamedTemporaryFile("w", suffix=".json") as d:
                if directory is not None:
                    json.dump(directory, d)
                    d.flush()
                    options["directory"] = d.name
                out = io.StringIO()
                call_command("import_dog_runs", stdout=out, **options)
        return out.getvalue()

    def test_addresses_from_the_directory(self):
        self.run_command(collection(feature(gispropnum="B111A")), [WASHINGTON])
        park = Place.objects.get(source_id="B163-DOGAREA0001")
        self.assertEqual(park.address, "3rd to 4th streets, 4th to 5th avenues")
        # Without the directory, the address is kept.
        self.run_command(
            collection(feature(gispropnum="B111A", name="Renamed Dog Run"))
        )
        park.refresh_from_db()
        self.assertEqual(park.name, "Renamed Dog Run")
        self.assertEqual(park.address, "3rd to 4th streets, 4th to 5th avenues")

    def test_adds_updates_and_hides(self):
        gone = Place.objects.create(
            name="Old Dog Run",
            category=Place.Category.DOG_PARK,
            source=Place.Source.NYC_PARKS,
            source_id="OLD-1",
            latitude=40.7,
            longitude=-73.9,
        )
        cafe = Place.objects.create(
            name="Bark & Brew Café", category="cafe", latitude=40.67, longitude=-73.98
        )
        out = self.run_command(collection(feature()))
        self.assertIn(
            "1 dog runs from NYC Open Data: 1 added, 0 updated, 1 no longer listed", out
        )
        park = Place.objects.get(source_id="B163-DOGAREA0001")
        self.assertEqual(park.category, Place.Category.DOG_PARK)
        self.assertIsNotNone(park.checked_on)
        gone.refresh_from_db()
        self.assertFalse(gone.is_active)
        cafe.refresh_from_db()
        self.assertTrue(cafe.is_active)  # places the team added are left alone

        out = self.run_command(
            collection(feature(name="Washington Park Dog Run (renamed)"))
        )
        self.assertIn("0 added, 1 updated, 0 no longer listed", out)
        park.refresh_from_db()
        self.assertEqual(park.name, "Washington Park Dog Run (renamed)")

    def test_nothing_changes_without_dog_runs(self):
        with self.assertRaisesMessage(CommandError, "No dog runs found"):
            self.run_command(collection())

    @mock.patch("places.management.commands.import_dog_runs.download")
    def test_downloads_by_default(self, download_mock):
        def fake_download(url=None):
            return (
                [WASHINGTON]
                if url == DIRECTORY_URL
                else collection(feature(gispropnum="B111A"))
            )

        download_mock.side_effect = fake_download
        call_command("import_dog_runs", stdout=io.StringIO())
        park = Place.objects.get(source_id="B163-DOGAREA0001")
        self.assertEqual(park.address, "3rd to 4th streets, 4th to 5th avenues")

    @mock.patch("places.management.commands.import_dog_runs.download")
    def test_directory_unreachable_keeps_addresses(self, download_mock):
        def fake_download(url=None):
            if url == DIRECTORY_URL:
                raise OpenDataUnavailable("offline")
            return collection(feature())

        download_mock.side_effect = fake_download
        out = io.StringIO()
        call_command("import_dog_runs", stdout=out)
        self.assertIn("kept the current addresses", out.getvalue())
        self.assertTrue(Place.objects.filter(source_id="B163-DOGAREA0001").exists())

    @mock.patch(
        "places.management.commands.import_dog_runs.download",
        side_effect=OpenDataUnavailable("offline"),
    )
    def test_open_data_unreachable(self, download_mock):
        with self.assertRaisesMessage(CommandError, "Couldn't reach NYC Open Data"):
            call_command("import_dog_runs", stdout=io.StringIO())

    def test_update_returns_counts(self):
        runs = dog_runs(collection(feature()))
        self.assertEqual(update_dog_parks(runs, date(2026, 11, 8)), (1, 0, 0))
