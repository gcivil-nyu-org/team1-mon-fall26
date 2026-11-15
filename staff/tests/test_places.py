"""#107 Manage Pet-Friendly Location Information: admins see every
pet-friendly place under Explore, as in Kat's 11/12 Figma, and can hide a
place from users (after confirming) or show it again. Hidden places
disappear from the Explore page users see."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from places.models import Place, PlaceReport

User = get_user_model()
LIST_URL = reverse("staff:place_list")
EXPLORE_URL = reverse("places:explore")


def detail_url(place):
    return reverse("staff:place_detail", args=[place.pk])


def make_place(name, category="cafe", **fields):
    defaults = {
        "address": "214 7th Ave",
        "borough": "Brooklyn",
        "latitude": Decimal("40.6710"),
        "longitude": Decimal("-73.9790"),
    }
    defaults.update(fields)
    return Place.objects.create(name=name, category=category, **defaults)


class PlaceTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Start without the places the data migration adds.
        Place.objects.all().delete()
        cls.admin = User.objects.create_user("admin", is_staff=True, first_name="Ada")
        cls.owner = User.objects.create_user("kat", first_name="Kat")
        AccountProfile.objects.create(user=cls.owner)
        cls.cafe = make_place(
            "Bark & Brew Café",
            hours="8 AM – 6 PM",
            features="Dogs welcome on the patio\nWater bowls and treats",
        )
        cls.park = make_place(
            "Maple Dog Run",
            "dog_park",
            address="",
            neighborhood="Prospect Park West & 3rd St",
            source=Place.Source.NYC_PARKS,
            source_id="B001",
        )
        cls.patio = make_place("Paws Patio", "restaurant", address="300 5th Ave")
        for details in ("Closes at 5 now", "Hours are wrong"):
            PlaceReport.objects.create(
                place=cls.cafe, reporter=cls.owner, details=details
            )
        PlaceReport.objects.create(
            place=cls.patio, reporter=cls.owner, details="Old", is_resolved=True
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def hide_url(self, place):
        return reverse("staff:hide_place", args=[place.pk])

    def show_url(self, place):
        return reverse("staff:show_place", args=[place.pk])


class AccessTests(PlaceTestData):
    def test_admins_only(self):
        self.client.logout()
        response = self.client.get(LIST_URL)
        self.assertRedirects(response, f"{reverse('login')}?next={LIST_URL}")
        self.client.force_login(self.owner)
        for url in (LIST_URL, detail_url(self.cafe)):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.hide_url(self.cafe)).status_code, 403)
        self.cafe.refresh_from_db()
        self.assertTrue(self.cafe.is_active)

    def test_explore_in_the_admin_menu(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{LIST_URL}" class="active">Explore</a>')
        self.assertContains(
            response, f'href="{reverse("staff:user_list")}" class="">Users</a>'
        )
        users = self.client.get(reverse("staff:user_list"))
        self.assertContains(users, f'href="{LIST_URL}" class="">Explore</a>')


class ListTests(PlaceTestData):
    def test_every_place_with_status_and_open_reports(self):
        response = self.client.get(LIST_URL)
        self.assertContains(
            response, '<h1 class="admin-title">Pet-friendly places</h1>'
        )
        self.assertEqual(
            [p.name for p in response.context["page"]],
            ["Bark & Brew Café", "Maple Dog Run", "Paws Patio"],
        )
        self.assertContains(response, "214 7th Ave, Brooklyn")
        self.assertContains(response, "Prospect Park West &amp; 3rd St, Brooklyn")
        self.assertContains(
            response, '<span class="staff-place-reports">2 reports</span>'
        )
        # A resolved report isn't counted.
        self.assertEqual(response.context["page"][2].open_reports, 0)
        self.assertContains(response, "Active", count=4)

    def test_tabs(self):
        self.patio.is_active = False
        self.patio.save()
        response = self.client.get(LIST_URL)
        self.assertEqual(
            [(t["label"], t["count"]) for t in response.context["tabs"]],
            [("All", 3), ("Hidden", 1)],
        )
        hidden = self.client.get(LIST_URL, {"tab": "hidden"})
        self.assertEqual(list(hidden.context["page"]), [self.patio])
        self.assertContains(hidden, f'href="{detail_url(self.patio)}?tab=hidden"')

    def test_no_hidden_places(self):
        response = self.client.get(LIST_URL, {"tab": "hidden"})
        self.assertContains(response, "No hidden places")
        self.assertIsNone(response.context["selected"])

    def test_no_places(self):
        Place.objects.all().delete()
        response = self.client.get(LIST_URL)
        self.assertContains(response, "No places yet")


class DetailTests(PlaceTestData):
    def test_first_place_is_open(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["selected"], self.cafe)

    def test_shows_the_place(self):
        response = self.client.get(detail_url(self.cafe))
        self.assertEqual(response.context["selected"], self.cafe)
        for text in (
            '<h2 id="place-name">Bark &amp; Brew Café</h2>',
            "<strong>2 reports open</strong>",
        ):
            self.assertContains(response, text, html=True)
        for text in (
            "Café",
            "8 AM – 6 PM",
            "Dogs welcome on the patio",
            "Water bowls and treats",
            "From the PawPal team",
            "Hide place",
        ):
            self.assertContains(response, text)

    def test_nothing_listed(self):
        response = self.client.get(detail_url(self.park))
        self.assertContains(response, "<dd>Not listed</dd>", html=True)
        self.assertContains(response, "None listed.")
        self.assertContains(response, "From NYC Parks on NYC Open Data")
        self.assertNotContains(response, "reports open")

    def test_unknown_place(self):
        self.assertEqual(self.client.get("/manage/places/9999/").status_code, 404)


class HideTests(PlaceTestData):
    def test_hide_asks_first(self):
        response = self.client.get(detail_url(self.cafe), {"confirm": "hide"})
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "Hide Bark &amp; Brew Café?")
        self.assertContains(response, f'action="{self.hide_url(self.cafe)}"')
        self.assertContains(response, f'href="{detail_url(self.cafe)}">Cancel</a>')
        self.cafe.refresh_from_db()
        self.assertTrue(self.cafe.is_active)

    def test_hiding_takes_it_off_explore(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(EXPLORE_URL), "Bark &amp; Brew Café")

        self.client.force_login(self.admin)
        response = self.client.post(self.hide_url(self.cafe), follow=True)
        self.assertRedirects(response, f"{detail_url(self.cafe)}?done=hidden")
        self.assertContains(response, "Hidden. Users can’t see this place.")
        self.assertContains(response, "Show place")
        self.assertNotContains(response, "confirm=hide")
        self.cafe.refresh_from_db()
        self.assertFalse(self.cafe.is_active)

        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(EXPLORE_URL), "Bark &amp; Brew Café")

    def test_hidden_place_without_the_banner(self):
        self.cafe.is_active = False
        self.cafe.save()
        response = self.client.get(detail_url(self.cafe), {"confirm": "hide"})
        self.assertContains(response, '<p class="staff-place-hidden" role="status">')
        self.assertNotContains(response, 'role="dialog"')

    def test_showing_it_again(self):
        self.cafe.is_active = False
        self.cafe.save()
        response = self.client.post(
            self.show_url(self.cafe), {"tab": "hidden"}, follow=True
        )
        self.assertRedirects(response, f"{detail_url(self.cafe)}?tab=hidden&done=shown")
        self.assertContains(response, "Shown. Users can see this place again.")
        self.cafe.refresh_from_db()
        self.assertTrue(self.cafe.is_active)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(EXPLORE_URL), "Bark &amp; Brew Café")

    def test_old_banner_link_doesnt_lie(self):
        response = self.client.get(detail_url(self.cafe), {"done": "hidden"})
        self.assertNotContains(response, "Hidden. Users")

    def test_search_is_kept(self):
        response = self.client.get(
            detail_url(self.cafe), {"q": "bark", "confirm": "hide"}
        )
        self.assertContains(response, '<input type="hidden" name="q" value="bark">')
        self.assertContains(
            response, f'href="{detail_url(self.cafe)}?q=bark">Cancel</a>'
        )
        response = self.client.post(self.hide_url(self.cafe), {"q": "bark"})
        self.assertRedirects(
            response,
            f"{detail_url(self.cafe)}?q=bark&done=hidden",
            fetch_redirect_response=False,
        )

    def test_post_only(self):
        self.assertEqual(self.client.get(self.hide_url(self.cafe)).status_code, 405)
        self.assertEqual(self.client.get(self.show_url(self.cafe)).status_code, 405)

    def test_hiding_twice_is_harmless(self):
        self.client.post(self.hide_url(self.cafe))
        response = self.client.post(self.hide_url(self.cafe))
        self.assertEqual(response.status_code, 302)
        self.cafe.refresh_from_db()
        self.assertFalse(self.cafe.is_active)


class SearchTests(PlaceTestData):
    def test_search_by_name_or_address(self):
        for q, expected in (("maple", [self.park]), ("300 5th", [self.patio])):
            response = self.client.get(LIST_URL, {"q": q})
            self.assertEqual(list(response.context["page"]), expected)
            self.assertContains(response, "1 place found")
        response = self.client.get(LIST_URL, {"q": "maple"})
        self.assertContains(response, f'href="{detail_url(self.park)}?q=maple"')

    def test_nothing_found(self):
        response = self.client.get(LIST_URL, {"q": "zzz"})
        self.assertContains(response, "No places found")
        self.assertContains(response, "Nothing matches “zzz”.")

    def test_pages(self):
        for i in range(25):
            make_place(f"Zed {i:02}")
        first = self.client.get(LIST_URL)
        self.assertEqual(len(first.context["page"]), 25)
        self.assertContains(first, "Page 1 of 2")
        second = self.client.get(LIST_URL, {"page": 2})
        self.assertEqual(len(second.context["page"]), 3)
        self.assertContains(second, "?page=2")
