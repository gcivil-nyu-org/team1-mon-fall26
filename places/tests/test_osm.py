"""Pet stores and dog-friendly cafés and restaurants from OpenStreetMap
(places/osm.py). Downloads are mocked; results look like the Overpass API's."""

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

from places.management.commands.import_osm_places import update_osm_places
from places.models import Place
from places.nyc_open_data import OpenDataUnavailable
from places.osm import QUERY, download, osm_places, weekly_hours

EXPLORE = reverse("places:explore")
NINE_TO_SIX = {"open": "09:00", "close": "18:00"}


def node(id=1, **tags):
    """One Overpass result: a café in Park Slope unless told otherwise."""
    base = {
        "name": "Lucky Dog Café",
        "amenity": "cafe",
        "dog": "yes",
        "addr:housenumber": "214",
        "addr:street": "7th Avenue",
        "addr:postcode": "11215-1234",
        "opening_hours": "Mo-Fr 09:00-18:00; Sa,Su 10:00-16:00",
    }
    base.update(tags)
    return {
        "type": "node",
        "id": id,
        "lat": 40.6716,
        "lon": -73.978,
        "tags": {k: v for k, v in base.items() if v is not None},
    }


def answer(*elements):
    return {"version": 0.6, "elements": list(elements)}


class HoursTests(SimpleTestCase):
    def test_simple_week(self):
        week = weekly_hours("Mo-Fr 09:00-18:00; Sa,Su 10:00-16:00")
        self.assertEqual(week[:5], [NINE_TO_SIX] * 5)
        self.assertEqual(week[5:], [{"open": "10:00", "close": "16:00"}] * 2)

    def test_days_not_listed_are_closed(self):
        week = weekly_hours("Tu-Sa 09:00-18:00")
        self.assertEqual(week, [None, *[NINE_TO_SIX] * 5, None])

    def test_off_and_later_rules_win(self):
        week = weekly_hours("Mo-Su 09:00-18:00; We off")
        self.assertIsNone(week[2])
        self.assertEqual(week[3], NINE_TO_SIX)

    def test_every_day_and_wrapping_ranges(self):
        self.assertEqual(weekly_hours("09:00-18:00"), [NINE_TO_SIX] * 7)
        week = weekly_hours("Fr-Mo 9:00-18:00")
        self.assertEqual([d is not None for d in week], [1, 0, 0, 0, 1, 1, 1])

    def test_past_midnight_and_holidays(self):
        week = weekly_hours("Mo-Sa 17:00-24:00; PH off")
        self.assertEqual(week[0], {"open": "17:00", "close": "00:00"})
        self.assertEqual(weekly_hours("Mo-Su 18:00-02:00")[0]["close"], "02:00")

    def test_anything_harder_shows_no_hours(self):
        for text in [
            "",
            None,
            "24/7",
            "Mo-Fr 11:00-15:00,17:00-22:00",
            "Mo-Fr 09:00-18:00 open",
            "Jan-Mar Mo 09:00-12:00",
            "Mo-Fr 25:00-26:00",
            "Mo-Fr 09:00-09:00",
            "Mo-Fr sunrise-sunset",
            "Mo off",
            "Mo-Xx 09:00-18:00",
            "Xy 09:00-18:00",
            "Mo 09:60-18:00",
            "Mo 9-18",
        ]:
            with self.subTest(text):
                self.assertEqual(weekly_hours(text), [])


class PlacesTests(SimpleTestCase):
    def test_a_cafe(self):
        [place] = osm_places(answer(node(outdoor_seating="yes")))
        self.assertEqual(place["source_id"], "node/1")
        self.assertEqual(place["name"], "Lucky Dog Café")
        self.assertEqual(place["category"], "cafe")
        self.assertEqual(place["address"], "214 7th Avenue")
        self.assertEqual(place["zip_code"], "11215")
        self.assertEqual(place["borough"], "Brooklyn")
        self.assertTrue(place["neighborhood"])
        self.assertEqual(place["latitude"], Decimal("40.671600"))
        self.assertEqual(place["weekly_hours"][0], NINE_TO_SIX)
        self.assertEqual(place["features"], "Dogs welcome inside\nOutdoor seating")

    def test_categories_and_dog_lines(self):
        places = osm_places(
            answer(
                node(1, name="Petco", amenity=None, dog=None, shop="pet"),
                node(2, name="Bark Bar", amenity="bar", dog="outside"),
                node(3, name="Gelato", amenity="ice_cream", dog="leashed"),
            )
        )
        by_name = {p["name"]: p for p in places}
        self.assertEqual(by_name["Petco"]["category"], "pet_store")
        self.assertEqual(by_name["Petco"]["features"], "Pet food and supplies")
        self.assertEqual(by_name["Bark Bar"]["category"], "restaurant")
        self.assertEqual(by_name["Bark Bar"]["features"], "Dogs welcome outside")
        self.assertEqual(by_name["Gelato"]["category"], "cafe")
        self.assertEqual(by_name["Gelato"]["features"], "Leashed dogs welcome")
        self.assertEqual([p["name"] for p in places], ["Bark Bar", "Gelato", "Petco"])

    def test_buildings_use_their_center(self):
        way = node(9)
        way.update(type="way", center={"lat": 40.7, "lon": -73.99})
        del way["lat"], way["lon"]
        [place] = osm_places(answer(way))
        self.assertEqual(place["source_id"], "way/9")
        self.assertEqual(place["latitude"], Decimal("40.700000"))

    def test_results_left_out(self):
        no_point = node(4)
        del no_point["lat"]
        self.assertEqual(
            osm_places(
                answer(
                    node(1, name=None),
                    node(2, name="   "),
                    {**node(3), "lat": 39.9},  # outside New York City
                    no_point,
                )
            ),
            [],
        )
        self.assertEqual(osm_places({}), [])
        self.assertEqual(osm_places(None), [])

    def test_no_street_no_address(self):
        [place] = osm_places(answer(node(**{"addr:street": None})))
        self.assertEqual(place["address"], "")

    def test_the_query_asks_for_all_of_nyc(self):
        self.assertIn('area["wikidata"="Q60"]', QUERY)
        self.assertIn('nwr["shop"="pet"]', QUERY)
        self.assertIn("cafe|fast_food|ice_cream|pub|restaurant", QUERY)
        self.assertIn("out center tags;", QUERY)

    @mock.patch("places.osm.urlopen")
    def test_download(self, urlopen):
        urlopen.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(answer(node())).encode()
        )
        self.assertEqual(len(download()["elements"]), 1)
        request = urlopen.call_args.args[0]
        self.assertIn(b"wikidata", request.data)
        urlopen.side_effect = TimeoutError("slow")
        with self.assertRaises(OpenDataUnavailable):
            download()


class UpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()

    def test_adds_updates_and_hides(self):
        today = timezone.localdate()
        gone = Place.objects.create(
            name="Closed Pet Shop",
            category="pet_store",
            source=Place.Source.OPENSTREETMAP,
            source_id="node/99",
            latitude=40.7,
            longitude=-73.9,
        )
        team = Place.objects.create(
            name="Our café", category="cafe", latitude=40.67, longitude=-73.98
        )
        self.assertEqual(
            update_osm_places(osm_places(answer(node())), today), (1, 0, 1)
        )
        place = Place.objects.get(source=Place.Source.OPENSTREETMAP, is_active=True)
        self.assertEqual(place.category, "cafe")
        self.assertEqual(place.checked_on, today)
        self.assertEqual(len(place.weekly_hours), 7)  # day-by-day hours
        gone.refresh_from_db()
        team.refresh_from_db()
        self.assertFalse(gone.is_active)
        self.assertTrue(team.is_active)

        # Shown again once it's back on the map, with its new details.
        place.is_active = False
        place.save()
        rows = osm_places(answer(node(name="Lucky Dog Coffee")))
        self.assertEqual(update_osm_places(rows, today), (0, 1, 0))
        place.refresh_from_db()
        self.assertTrue(place.is_active)
        self.assertEqual(place.name, "Lucky Dog Coffee")

    def test_admin_edits_are_kept(self):
        Place.objects.create(
            name="Fixed by an admin",
            category="cafe",
            source=Place.Source.OPENSTREETMAP,
            source_id="node/1",
            latitude=40.6,
            longitude=-74.0,
            edited_at=timezone.now(),
        )
        rows = osm_places(answer(node()))
        self.assertEqual(update_osm_places(rows, timezone.localdate()), (0, 0, 0))
        self.assertEqual(Place.objects.get().name, "Fixed by an admin")


class CommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()

    def run_command(self, **options):
        out = io.StringIO()
        call_command("import_osm_places", stdout=out, **options)
        return out.getvalue()

    @mock.patch("places.management.commands.import_osm_places.download")
    def test_downloads_from_openstreetmap(self, download):
        download.return_value = answer(
            node(1), node(2, name="Petco", amenity=None, dog=None, shop="pet")
        )
        out = self.run_command()
        self.assertIn("2 places from OpenStreetMap (1 café, 1 pet store)", out)
        self.assertIn("2 added, 0 updated, 0 no longer listed", out)

    def test_reads_a_saved_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump(answer(node()), f)
            f.flush()
            self.run_command(file=f.name)
        self.assertEqual(Place.objects.filter(source="osm").count(), 1)

    @mock.patch(
        "places.management.commands.import_osm_places.download",
        side_effect=OpenDataUnavailable("down"),
    )
    def test_nothing_changes_when_unreachable(self, download):
        with self.assertRaisesMessage(CommandError, "Couldn't reach OpenStreetMap"):
            self.run_command()

    @mock.patch("places.management.commands.import_osm_places.download")
    def test_nothing_changes_without_data(self, download):
        download.return_value = ["not", "a", "dict"]
        with self.assertRaisesMessage(CommandError, "something unexpected"):
            self.run_command()
        download.return_value = answer()
        with self.assertRaisesMessage(CommandError, "No places found"):
            self.run_command()


class ExploreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()
        cls.owner = get_user_model().objects.create_user("kat", password="pw-12345!")
        cls.cafe = Place.objects.create(
            name="Lucky Dog Café",
            category="cafe",
            source=Place.Source.OPENSTREETMAP,
            source_id="node/42",
            address="214 7th Avenue",
            borough="Brooklyn",
            latitude="40.6716",
            longitude="-73.9780",
            features="Dogs welcome inside",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_cafe_card_credits_openstreetmap(self):
        response = self.client.get(
            EXPLORE, {"category": "cafe", "location": "Park Slope"}
        )
        self.assertEqual(response.context["places"], [self.cafe])
        self.assertContains(response, "Dogs welcome inside")
        self.assertContains(response, 'href="https://www.openstreetmap.org/node/42"')
        self.assertContains(response, ">OpenStreetMap</a>")

    def test_source_names(self):
        self.assertEqual(self.cafe.source_name(), "OpenStreetMap")
        self.assertEqual(Place(source=Place.Source.PAWPAL).source_name(), "PawPal team")
        self.assertEqual(
            Place(source=Place.Source.NYC_PARKS).source_name(), "NYC Open Data"
        )
        self.assertEqual(Place(source=Place.Source.OPENSTREETMAP).source_url(), "")
