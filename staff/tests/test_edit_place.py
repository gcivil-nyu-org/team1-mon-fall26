"""#107 Manage Pet-Friendly Location Information: an admin corrects a place's
details (Figma "Manage Pet-Friendly Location Information (Edit)" / "(Saved)")
and users see the change on Explore. A new address moves the map pin."""

from decimal import Decimal
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from caregivers.geocoding import GeocodingUnavailable, Location
from places.models import Place

from .test_places import EXPLORE_URL, PlaceTestData, detail_url

FIFTH_AVE = Location(
    latitude=Decimal("40.668000"),
    longitude=Decimal("-73.981000"),
    neighborhood="Park Slope",
    borough="Brooklyn",
)


def edit_url(place):
    return reverse("staff:edit_place", args=[place.pk])


class EditPlaceTests(PlaceTestData):
    def data(self, **changes):
        fields = {
            "name": "Bark & Brew Café",
            "category": "cafe",
            "address": "214 7th Ave",
            "neighborhood": "",
            "borough": "Brooklyn",
            "zip_code": "",
            "hours": "8 AM – 5 PM",
            "features": "Dogs welcome on the patio\nWater bowls and treats",
        }
        fields.update(changes)
        return fields

    def save(self, place=None, **changes):
        return self.client.post(edit_url(place or self.cafe), self.data(**changes))

    def test_edit_details_opens_the_form(self):
        response = self.client.get(detail_url(self.cafe))
        self.assertContains(
            response, f'href="{detail_url(self.cafe)}?edit=1">Edit details</a>'
        )
        response = self.client.get(detail_url(self.cafe), {"edit": "1"})
        self.assertContains(response, f'action="{edit_url(self.cafe)}"')
        self.assertContains(response, 'value="Bark &amp; Brew Café"')
        self.assertContains(response, "Water bowls and treats</textarea>")
        self.assertContains(response, "Save changes")
        self.assertContains(response, f'href="{detail_url(self.cafe)}">Cancel</a>')
        self.assertNotContains(response, "Edit details</a>")

    def test_get_goes_to_the_form(self):
        response = self.client.get(edit_url(self.cafe))
        self.assertRedirects(response, f"{detail_url(self.cafe)}?edit=1")

    @mock.patch("staff.place_forms.geocode")
    def test_saves_and_users_see_it(self, geocode):
        response = self.save(
            name="Bark & Brew", hours="8 AM – 5 PM", features="Pup cups"
        )
        self.assertRedirects(response, f"{detail_url(self.cafe)}?done=saved")
        geocode.assert_not_called()  # Same address, same pin.
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.name, "Bark & Brew")
        self.assertEqual(self.cafe.hours, "8 AM – 5 PM")
        self.assertEqual(self.cafe.feature_list(), ["Pup cups"])
        self.assertEqual(self.cafe.checked_on, timezone.localdate())

        page = self.client.get(f"{detail_url(self.cafe)}?done=saved")
        self.assertContains(
            page, "Changes saved. Users see the new details on Explore."
        )

        self.client.force_login(self.owner)
        explore = self.client.get(EXPLORE_URL)
        self.assertContains(explore, "Bark &amp; Brew")
        self.assertContains(explore, "Pup cups")
        self.assertNotContains(explore, "Bark &amp; Brew Café")

    @mock.patch("staff.place_forms.geocode", return_value=FIFTH_AVE)
    def test_new_address_moves_the_pin(self, geocode):
        self.save(address="300 5th Ave")
        geocode.assert_called_once_with("300 5th Ave, Brooklyn")
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.address, "300 5th Ave")
        self.assertEqual(self.cafe.latitude, Decimal("40.668000"))
        self.assertEqual(self.cafe.longitude, Decimal("-73.981000"))

    @mock.patch("staff.place_forms.geocode", return_value=None)
    def test_address_outside_nyc(self, geocode):
        response = self.save(address="1 Main St, Boston")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "We couldn&#x27;t find this address in New York City."
        )
        self.assertContains(response, "Almost there.")
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.address, "214 7th Ave")

    @mock.patch("staff.place_forms.geocode", side_effect=GeocodingUnavailable("down"))
    def test_saves_when_the_lookup_is_down(self, geocode):
        response = self.save(address="300 5th Ave")
        self.assertRedirects(
            response,
            f"{detail_url(self.cafe)}?done=saved&unlocated=1",
            fetch_redirect_response=False,
        )
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.address, "300 5th Ave")
        self.assertEqual(self.cafe.latitude, Decimal("40.671000"))
        page = self.client.get(response["Location"])
        self.assertContains(page, "the map pin didn’t move")

    def test_name_and_location_are_required(self):
        response = self.save(name="  ", address="", neighborhood="")
        self.assertContains(response, "Enter the place&#x27;s name.")
        self.assertContains(response, "Add an address or the cross streets.")
        self.cafe.refresh_from_db()
        self.assertEqual(self.cafe.name, "Bark & Brew Café")

    def test_cross_streets_are_enough(self):
        response = self.client.post(
            edit_url(self.park),
            self.data(
                name="Maple Dog Run",
                category="dog_park",
                address="",
                neighborhood="Prospect Park West & 4th St",
            ),
        )
        self.assertRedirects(response, f"{detail_url(self.park)}?done=saved")
        self.park.refresh_from_db()
        self.assertEqual(self.park.neighborhood, "Prospect Park West & 4th St")

    def test_hidden_tab_and_search_are_kept(self):
        self.cafe.is_active = False
        self.cafe.save()
        response = self.client.post(
            edit_url(self.cafe), {**self.data(), "tab": "hidden", "q": "bark"}
        )
        self.assertRedirects(
            response,
            f"{detail_url(self.cafe)}?tab=hidden&q=bark&done=saved",
            fetch_redirect_response=False,
        )
        self.cafe.refresh_from_db()
        self.assertFalse(self.cafe.is_active)

    def test_admins_only(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.save().status_code, 403)
        self.assertEqual(Place.objects.get(pk=self.cafe.pk).hours, "8 AM – 6 PM")
