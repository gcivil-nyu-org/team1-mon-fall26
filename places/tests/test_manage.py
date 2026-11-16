"""Story #107, Manage Pet-Friendly Location Information: the admin
"Pet-friendly places" page (Figma "Manage Pet-Friendly Location" frames).
Address lookups are mocked."""

from datetime import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.geocoding import GeocodingUnavailable, Location
from places.forms import split_borough
from places.management.commands.import_dog_runs import update_dog_parks
from places.models import Place, PlaceReport, time_label

User = get_user_model()
MANAGE = reverse("places:manage")

# Tuesday, Nov 17, 2026 in New York.
TUESDAY_NOON = timezone.make_aware(datetime(2026, 11, 17, 12, 0))

NINE_TO_FIVE = {"open": "09:00", "close": "17:00"}


def at(hour, minute=0, day=17):
    return timezone.make_aware(datetime(2026, 11, day, hour, minute))


class ManageData(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()
        cls.admin = User.objects.create_user(
            "admin", password="pw-12345!", first_name="Ada", is_staff=True
        )
        cls.owner = User.objects.create_user(
            "kat", password="pw-12345!", first_name="Kat", last_name="Wong"
        )
        cls.cafe = Place.objects.create(
            name="Bark & Brew Café",
            category="cafe",
            address="214 7th Ave",
            borough="Brooklyn",
            latitude="40.6716",
            longitude="-73.9780",
            weekly_hours=[NINE_TO_FIVE] * 6 + [None],
            features="Dogs welcome on the patio\nWater bowls and treats",
        )
        cls.park = Place.objects.create(
            name="Maple Dog Run",
            category="dog_park",
            address="Prospect Park West & 3rd St",
            borough="Brooklyn",
            latitude="40.6700",
            longitude="-73.9700",
            source=Place.Source.NYC_PARKS,
            source_id="B-1",
        )
        cls.patio = Place.objects.create(
            name="Paws Patio",
            category="restaurant",
            address="300 5th Ave",
            borough="Brooklyn",
            latitude="40.6720",
            longitude="-73.9850",
            hours="Open daily 11 AM – 10 PM",
            is_active=False,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def detail(self, place, **params):
        url = reverse("places:manage_detail", args=[place.pk])
        return self.client.get(url, params)

    def edit_url(self, place):
        return reverse("places:manage_edit", args=[place.pk])

    def form_data(self, **changes):
        data = {
            "name": "Bark & Brew Café",
            "category": "cafe",
            "address": "214 7th Ave, Brooklyn",
            "amenity": ["Dogs welcome on the patio", "Water bowls and treats"],
        }
        for day in ["mon", "tue", "wed", "thu", "fri", "sat"]:
            data.update(
                {f"{day}_open": "on", f"{day}_from": "08:00", f"{day}_to": "17:00"}
            )
        data.update({"sun_from": "09:00", "sun_to": "17:00"})
        data.update(changes)
        return data


class AccessTests(ManageData):
    def test_signed_out_and_regular_users(self):
        self.client.logout()
        response = self.client.get(MANAGE)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.client.force_login(self.owner)
        for url in (
            MANAGE,
            reverse("places:manage_detail", args=[self.cafe.pk]),
            self.edit_url(self.cafe),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)
        hide = reverse("places:manage_hide", args=[self.cafe.pk])
        self.assertEqual(self.client.post(hide).status_code, 403)
        self.cafe.refresh_from_db()
        self.assertTrue(self.cafe.is_active)

    def test_explore_in_the_admin_header(self):
        response = self.client.get(MANAGE)
        self.assertContains(response, f'<a href="{MANAGE}" class="active">Explore</a>')
        self.assertContains(
            response, '<h1 class="admin-title">Pet-friendly places</h1>'
        )


class ListTests(ManageData):
    def test_tabs_and_rows(self):
        PlaceReport.objects.create(place=self.patio, reporter=self.owner, details="x")
        response = self.client.get(MANAGE)
        tabs = {t["key"]: t["count"] for t in response.context["tabs"]}
        self.assertEqual(tabs, {"all": 3, "hidden": 1})
        names = [p.name for p in response.context["page"]]
        # Places with open reports first, then by name.
        self.assertEqual(names, ["Paws Patio", "Bark & Brew Café", "Maple Dog Run"])
        self.assertEqual(response.context["selected"], self.patio)
        self.assertContains(response, "1 report</span>")
        self.assertContains(response, "214 7th Ave, Brooklyn")
        self.assertContains(response, "Active</span>")
        self.assertContains(response, "Hidden</span>")

    def test_hidden_tab(self):
        response = self.client.get(MANAGE, {"tab": "hidden"})
        self.assertEqual([p.name for p in response.context["page"]], ["Paws Patio"])
        self.assertEqual(self.client.get(MANAGE, {"tab": "nope"}).context["tab"], "all")

    def test_search(self):
        response = self.client.get(MANAGE, {"q": "maple"})
        self.assertEqual(list(response.context["page"]), [self.park])
        self.assertContains(response, "1 place found")
        response = self.client.get(MANAGE, {"q": "zzz"})
        self.assertContains(response, "No places match “zzz”.")
        self.assertIsNone(response.context["selected"])
        # Links to a place keep the search.
        response = self.client.get(MANAGE, {"q": "brew", "tab": "all"})
        self.assertContains(response, f"/places/manage/{self.cafe.pk}/?q=brew")

    def test_empty_hidden_tab(self):
        self.patio.is_active = True
        self.patio.save()
        response = self.client.get(MANAGE, {"tab": "hidden"})
        self.assertContains(response, "No hidden places.")

    def test_pages(self):
        for n in range(25):
            Place.objects.create(
                name=f"Run {n:02d}", category="dog_park", latitude=40.7, longitude=-74
            )
        response = self.client.get(MANAGE)
        self.assertContains(response, "Page 1 of 2")
        response = self.client.get(MANAGE, {"page": 2, "q": "run"})
        self.assertContains(response, "Page 2 of 2")
        self.assertContains(response, "?q=run&amp;page=2")


class DetailTests(ManageData):
    def test_figma_detail(self):
        response = self.detail(self.cafe)
        self.assertContains(response, '<h2 id="place-title">Bark &amp; Brew Café</h2>')
        self.assertContains(response, "9 AM – 5 PM")
        self.assertContains(response, 'class="is-closed">Closed</dd>')
        self.assertContains(response, "Dogs welcome on the patio")
        self.assertContains(response, "Edit details")
        self.assertContains(response, "Hide place")
        self.assertNotContains(response, "report open")
        self.assertEqual(len(response.context["week"]), 7)
        self.assertIn(response.context["open_now"], (True, False))

    def test_reports_bar_links_to_reports(self):
        PlaceReport.objects.create(place=self.cafe, reporter=self.owner, details="a")
        newest = PlaceReport.objects.create(
            place=self.cafe, reporter=self.admin, details="b"
        )
        PlaceReport.objects.create(
            place=self.cafe, reporter=self.owner, details="c", status="resolved"
        )
        response = self.detail(self.cafe)
        self.assertContains(response, "2 reports open")
        self.assertContains(response, reverse("reports:admin_place", args=[newest.pk]))

    def test_text_hours_or_none(self):
        response = self.detail(self.patio)
        self.assertContains(response, "Open daily 11 AM – 10 PM")
        self.assertContains(response, "Hidden. Users can't see this place.")
        self.assertContains(response, "Show place")
        self.assertNotContains(response, "Hide place")
        response = self.detail(self.park)
        self.assertContains(response, "Not listed yet")
        self.assertContains(response, "None listed yet.")
        self.assertIsNone(response.context["open_now"])

    def test_done_banners(self):
        response = self.detail(self.cafe, done="saved")
        self.assertContains(response, "Changes saved. Users see the update.")
        response = self.detail(self.cafe, done="other")
        self.assertIsNone(response.context["done"])

    def test_missing_place(self):
        url = reverse("places:manage_detail", args=[999])
        self.assertEqual(self.client.get(url).status_code, 404)


class HideShowTests(ManageData):
    def test_hide_asks_first(self):
        response = self.detail(self.cafe, confirm="hide")
        self.assertContains(response, "Hide this place?")
        self.assertContains(
            response, "Users won't see this place until you show it again."
        )
        # A hidden place has nothing to confirm.
        response = self.detail(self.patio, confirm="hide")
        self.assertNotContains(response, "Hide this place?")

    def test_hide_and_show(self):
        hide = reverse("places:manage_hide", args=[self.cafe.pk])
        self.assertEqual(self.client.get(hide).status_code, 405)
        response = self.client.post(hide + "?tab=all&q=brew")
        self.assertRedirects(
            response,
            reverse("places:manage_detail", args=[self.cafe.pk]) + "?q=brew",
            fetch_redirect_response=False,
        )
        self.cafe.refresh_from_db()
        self.assertFalse(self.cafe.is_active)
        self.assertIsNotNone(self.cafe.edited_at)
        # Users can't see it on Explore.
        self.client.force_login(self.owner)
        explore = self.client.get(reverse("places:explore"))
        self.assertNotIn(self.cafe, explore.context["places"])

        self.client.force_login(self.admin)
        show = reverse("places:manage_show", args=[self.cafe.pk])
        response = self.client.post(show + "?tab=hidden")
        self.assertRedirects(
            response,
            reverse("places:manage_detail", args=[self.cafe.pk])
            + "?tab=hidden&done=shown",
            fetch_redirect_response=False,
        )
        self.cafe.refresh_from_db()
        self.assertTrue(self.cafe.is_active)


class EditTests(ManageData):
    def test_form_matches_figma(self):
        response = self.client.get(self.edit_url(self.cafe))
        self.assertContains(response, 'value="Bark &amp; Brew Café"')
        self.assertContains(response, 'value="214 7th Ave, Brooklyn"')
        self.assertContains(response, ">Dog park</span>")
        self.assertContains(response, 'name="mon_open" id="id_mon_open" checked')
        self.assertContains(response, 'name="sun_open" id="id_sun_open" aria')
        self.assertContains(response, 'name="mon_from" value="09:00"')
        self.assertContains(response, 'value="Water bowls and treats"')
        self.assertContains(response, "+ Add amenity")
        self.assertContains(response, "Save changes")

    def test_save(self):
        data = self.form_data(
            name=" Bark & Brew ",
            category="restaurant",
            amenity=["Water bowls", " ", "Dog menu"],
            fri_to="20:00",
            sat_from="09:00",
        )
        response = self.client.post(self.edit_url(self.cafe) + "?q=brew", data)
        self.assertRedirects(
            response,
            reverse("places:manage_detail", args=[self.cafe.pk]) + "?q=brew&done=saved",
            fetch_redirect_response=False,
        )
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.name, "Bark & Brew")
        self.assertEqual(self.cafe.category, "restaurant")
        self.assertEqual(self.cafe.features, "Water bowls\nDog menu")
        self.assertEqual(self.cafe.weekly_hours[0], {"open": "08:00", "close": "17:00"})
        self.assertEqual(self.cafe.weekly_hours[4], {"open": "08:00", "close": "20:00"})
        self.assertIsNone(self.cafe.weekly_hours[6])
        self.assertIsNotNone(self.cafe.edited_at)
        # The address didn't change, so the pin stays.
        self.assertEqual(self.cafe.latitude, Decimal("40.671600"))

    def test_every_type_has_a_chip(self):
        # Off-leash areas and dog fountains came from later imports; editing
        # one used to fail with "Pick a type." because it had no chip.
        response = self.client.get(self.edit_url(self.cafe))
        for value, label in Place.Category.choices:
            self.assertContains(response, f'value="{value}"')
        for category in (Place.Category.OFF_LEASH, Place.Category.DOG_FOUNTAIN):
            data = self.form_data(category=category)
            response = self.client.post(self.edit_url(self.cafe), data)
            self.assertEqual(response.status_code, 302)
            self.cafe.refresh_from_db()
            self.assertEqual(self.cafe.category, category)

    def test_day_by_day_hours_replace_text_hours(self):
        data = self.form_data(name="Paws Patio", category="restaurant", address="")
        data["address"] = "300 5th Ave, Brooklyn"
        self.client.post(self.edit_url(self.patio), data)
        self.patio.refresh_from_db()
        self.assertEqual(self.patio.hours, "")
        self.assertEqual(len(self.patio.weekly_hours), 7)

    def test_no_days_on_keeps_text_hours(self):
        data = {
            "name": "Paws Patio",
            "category": "restaurant",
            "address": "300 5th Ave, Brooklyn",
        }
        self.client.post(self.edit_url(self.patio), data)
        self.patio.refresh_from_db()
        self.assertEqual(self.patio.hours, "Open daily 11 AM – 10 PM")
        self.assertEqual(self.patio.weekly_hours, [])
        # Switching every day off on a place with day-by-day hours clears them.
        data = {"name": "Café", "category": "cafe", "address": "214 7th Ave, Brooklyn"}
        self.client.post(self.edit_url(self.cafe), data)
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.weekly_hours, [])

    def test_required_fields(self):
        response = self.client.post(self.edit_url(self.cafe), {"name": " "})
        self.assertContains(response, "Almost there.")
        self.assertContains(response, "Add a name.")
        self.assertContains(response, "Pick a type.")
        self.assertContains(response, "Add an address.")
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.name, "Bark & Brew Café")

    def test_bad_hours(self):
        data = self.form_data(mon_from="", tue_to="08:00", wed_from="9 o'clock")
        response = self.client.post(self.edit_url(self.cafe), data)
        self.assertContains(response, "Add when it opens and closes.")
        self.assertContains(response, "Use a time like 8:00 AM.")
        data = self.form_data(tue_from="08:00", tue_to="08:00")
        response = self.client.post(self.edit_url(self.cafe), data)
        self.assertContains(response, "Opening and closing can&#x27;t match.")

    def test_amenity_limits(self):
        data = self.form_data(amenity=[f"Thing {n}" for n in range(11)])
        response = self.client.post(self.edit_url(self.cafe), data)
        self.assertContains(response, "Keep it to 10 amenities.")
        data = self.form_data(amenity=["x" * 81])
        response = self.client.post(self.edit_url(self.cafe), data)
        self.assertContains(response, "Keep each amenity under 80 characters.")

    @mock.patch("places.admin_views.geocode")
    def test_new_address_moves_the_pin(self, geocode):
        geocode.return_value = Location(
            latitude=Decimal("40.668"),
            longitude=Decimal("-73.981"),
            neighborhood="Park Slope",
            borough="Brooklyn",
        )
        data = self.form_data(address="250 7th Ave, Brooklyn")
        response = self.client.post(self.edit_url(self.cafe), data)
        self.assertTrue(response.url.endswith("done=saved"))
        geocode.assert_called_once_with("250 7th Ave, Brooklyn")
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.address, "250 7th Ave")
        self.assertEqual(self.cafe.latitude, Decimal("40.668"))
        self.assertEqual(self.cafe.neighborhood, "Park Slope")

    @mock.patch("places.admin_views.geocode", return_value=None)
    def test_unknown_address_keeps_the_pin(self, geocode):
        response = self.client.post(
            self.edit_url(self.cafe), self.form_data(address="9999 Nowhere St")
        )
        self.assertTrue(response.url.endswith("done=saved_pin"))
        geocode.assert_called_once_with("9999 Nowhere St, Brooklyn")
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.address, "9999 Nowhere St")
        self.assertEqual(self.cafe.latitude, Decimal("40.671600"))
        response = self.detail(self.cafe, done="saved_pin")
        self.assertContains(response, "so the pin stayed where it was")

    @mock.patch("places.admin_views.geocode", side_effect=GeocodingUnavailable("down"))
    def test_lookup_down_keeps_the_pin(self, geocode):
        response = self.client.post(
            self.edit_url(self.cafe), self.form_data(address="250 7th Ave, Queens")
        )
        self.assertTrue(response.url.endswith("done=saved_pin"))
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.borough, "Queens")

    @mock.patch("places.admin_views.geocode")
    def test_cross_streets_are_not_looked_up(self, geocode):
        data = self.form_data(
            name="Maple Dog Run",
            category="dog_park",
            address="Prospect Park West & 4th St, Brooklyn",
        )
        response = self.client.post(self.edit_url(self.park), data)
        self.assertTrue(response.url.endswith("done=saved_pin"))
        geocode.assert_not_called()
        self.park.refresh_from_db()
        self.assertEqual(self.park.address, "Prospect Park West & 4th St")


class HoursTests(SimpleTestCase):
    def test_time_label(self):
        self.assertEqual(time_label("08:00"), "8 AM")
        self.assertEqual(time_label("17:30"), "5:30 PM")
        self.assertEqual(time_label("00:00"), "12 AM")
        self.assertEqual(time_label("12:00"), "12 PM")

    def test_week_and_open_now(self):
        place = Place(weekly_hours=[NINE_TO_FIVE] * 5 + [None, None])
        week = place.week(TUESDAY_NOON)
        self.assertEqual(
            week[1], {"name": "Tue", "hours": "9 AM – 5 PM", "is_today": True}
        )
        self.assertIsNone(week[6]["hours"])
        self.assertTrue(place.is_open_now(TUESDAY_NOON))
        self.assertFalse(place.is_open_now(at(8, 59)))
        self.assertFalse(place.is_open_now(at(17)))
        self.assertEqual(place.hours_line(TUESDAY_NOON), "Open today 9 AM – 5 PM")
        self.assertEqual(place.hours_line(at(12, day=21)), "Closed today")
        self.assertEqual(Place().week(), [])
        self.assertIsNone(Place().is_open_now())

    def test_hours_past_midnight(self):
        late = {"open": "18:00", "close": "02:00"}
        place = Place(weekly_hours=[late, None, None, None, None, None, None])
        monday = 16
        self.assertTrue(place.is_open_now(at(23, day=monday)))
        self.assertFalse(place.is_open_now(at(17, day=monday)))
        # Still open early Tuesday morning, from Monday night.
        self.assertTrue(place.is_open_now(at(1, 30)))
        self.assertFalse(place.is_open_now(at(2, 30)))

    def test_split_borough(self):
        self.assertEqual(
            split_borough("214 7th Ave, Brooklyn"), ("214 7th Ave", "Brooklyn")
        )
        self.assertEqual(split_borough("1 Main St, The Bronx"), ("1 Main St", "Bronx"))
        self.assertEqual(
            split_borough("1 Main St, Hoboken"), ("1 Main St, Hoboken", "")
        )
        self.assertEqual(split_borough(", Queens"), (", Queens", ""))


class ImportKeepsAdminEditsTests(TestCase):
    def test_edited_dog_parks_are_left_alone(self):
        Place.objects.all().delete()
        run = {
            "source_id": "B-1",
            "name": "From NYC Parks",
            "borough": "Brooklyn",
            "zip_code": "11215",
            "neighborhood": "Park Slope",
            "latitude": Decimal("40.67"),
            "longitude": Decimal("-73.97"),
            "features": "Off-leash",
        }
        edited = Place.objects.create(
            name="Fixed by an admin",
            category="dog_park",
            source=Place.Source.NYC_PARKS,
            source_id="B-1",
            latitude=40.6,
            longitude=-73.9,
            edited_at=timezone.now(),
        )
        gone = Place.objects.create(
            name="Not listed anymore",
            category="dog_park",
            source=Place.Source.NYC_PARKS,
            source_id="B-2",
            latitude=40.6,
            longitude=-73.9,
            edited_at=timezone.now(),
        )
        added, updated, hidden = update_dog_parks([run], timezone.localdate())
        self.assertEqual((added, updated, hidden), (0, 0, 0))
        edited.refresh_from_db()
        gone.refresh_from_db()
        self.assertEqual(edited.name, "Fixed by an admin")
        self.assertTrue(gone.is_active)
