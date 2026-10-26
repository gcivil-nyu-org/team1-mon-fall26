"""Tests for the Find caregivers filters: #34 Filter Caregivers by Service and
#35 Filter Caregivers by Availability."""

from decimal import Decimal

from django.urls import reverse

from caregivers.models import CaregiverService, ServiceType
from caregivers.search import (
    offered_service_types,
    offering_service,
    searchable_caregivers,
)

from .test_search import NYU, URL, SearchTestData

BOOKING_URL = reverse("bookings:booking_create")


class FilterTestData(SearchTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Chloe already walks dogs for $25 (see SearchTestData).
        cls.sitting = ServiceType.objects.get_or_create(name="Pet sitting")[0]
        cls.grooming = ServiceType.objects.get_or_create(name="Grooming")[0]
        cls.offer(cls.midtown, cls.walking, "30.00")
        cls.offer(cls.midtown, cls.sitting, "60.00")
        cls.offer(cls.lic, cls.sitting, "55.00")
        # Switched off, so not shown. A price is optional.
        cls.offer(cls.boerum, cls.sitting, "40.00", is_active=False)
        cls.offer(cls.staten, cls.grooming, None)
        # Not taking new bookings, but offers walks.
        cls.busy = cls.make("Busy", "40.731", "-73.995", hood="Greenwich Village",
                            accepting_new_bookings=False)
        cls.offer(cls.busy, cls.walking, "20.00")

    @classmethod
    def offer(cls, caregiver, service_type, price, is_active=True):
        return CaregiverService.objects.create(
            caregiver=caregiver, service_type=service_type,
            price=Decimal(price) if price else None, is_active=is_active,
        )


class ServiceFilterHelperTests(FilterTestData):
    def test_offered_service_types_are_active_ones_with_or_without_a_price(self):
        self.assertEqual(
            [st.name for st in offered_service_types()],
            ["Dog walking", "Grooming", "Pet sitting"],
        )

    def test_offering_service(self):
        caregivers = offering_service(searchable_caregivers(self.owner), self.sitting)
        self.assertEqual([c.name for c in caregivers], ["Alicia", "Marcus"])


class FilterByServiceTests(FilterTestData):
    """#34: owners pick a service and only caregivers who offer it appear."""

    def test_owner_can_see_the_service_types(self):
        response = self.client.get(URL)
        # "All services" is the selected chip when no filter is on.
        self.assertContains(
            response,
            '<a class="filter-chip is-active" href="?" aria-current="true">All services</a>',
            html=True,
        )
        self.assertContains(
            response,
            f'<a class="filter-chip" href="?service={self.walking.pk}">Dog walking</a>',
            html=True,
        )
        self.assertContains(
            response,
            f'<a class="filter-chip" href="?service={self.sitting.pk}">Pet sitting</a>',
            html=True,
        )
        # Grooming has no price yet, but it's offered, so it's a filter too.
        self.assertContains(
            response,
            f'<a class="filter-chip" href="?service={self.grooming.pk}">Grooming</a>',
            html=True,
        )

    def test_only_caregivers_offering_the_service_appear(self):
        response = self.client.get(URL, {"service": self.sitting.pk})
        self.assertEqual(self.names(response), ["Alicia", "Marcus"])
        self.assertContains(response, "2 caregivers on PawPal · Pet sitting")

    def test_inactive_or_unpriced_services_do_not_count(self):
        response = self.client.get(URL, {"service": self.sitting.pk})
        self.assertNotIn("Priya", self.names(response))

    def test_selected_service_chip_is_highlighted(self):
        response = self.client.get(URL, {"service": self.walking.pk})
        chips = response.content.decode().split('class="filter-chip is-active"')
        # Only one chip is selected: Dog walking, not "All services".
        self.assertEqual(len(chips), 2)
        self.assertIn("Dog walking", chips[1].split("</a>")[0])
        self.assertContains(
            response,
            '<a class="filter-chip" href="?">All services</a>',
            html=True,
        )

    def test_selected_service_is_shown_first_on_the_card(self):
        response = self.client.get(URL, {"service": self.sitting.pk})
        alicia = next(c for c in response.context["caregivers"] if c.name == "Alicia")
        self.assertEqual(
            [s.service_type.name for s in alicia.listed_services],
            ["Pet sitting", "Dog walking"],
        )
        self.assertContains(response, 'class="service-chip is-match"')

    def test_owner_can_change_the_service(self):
        walking = self.client.get(URL, {"service": self.walking.pk})
        sitting = self.client.get(URL, {"service": self.sitting.pk})
        self.assertEqual(self.names(walking), ["Alicia", "Chloe"])
        self.assertEqual(self.names(sitting), ["Alicia", "Marcus"])

    def test_owner_can_remove_the_filter(self):
        response = self.client.get(URL, {"service": self.walking.pk})
        self.assertContains(response, "Clear filter")
        self.assertEqual(response.context["query_without_service"], "")
        everyone = self.client.get(URL)
        self.assertEqual(self.names(everyone), ["Alicia", "Chloe", "Marcus", "Priya", "Sam"])
        self.assertNotContains(everyone, "Clear filter")

    def test_selected_chip_clears_the_filter(self):
        response = self.client.get(URL, {"service": self.walking.pk, "distance": "2"})
        active = response.content.decode().split('class="filter-chip is-active"')[1]
        self.assertTrue(active.startswith(' href="?distance=2"'))

    def test_chips_keep_the_location_and_distance(self):
        response = self.client.get(URL, {"location": "x", **NYU, "distance": "2"})
        chip = next(
            c for c in response.context["service_filters"] if c["type"] == self.sitting
        )
        self.assertIn(f"service={self.sitting.pk}", chip["query"])
        self.assertIn("lat=40.729", chip["query"])
        self.assertIn("distance=2", chip["query"])

    def test_switching_chips_replaces_the_service(self):
        response = self.client.get(URL, {"service": self.walking.pk})
        chip = next(
            c for c in response.context["service_filters"] if c["type"] == self.sitting
        )
        self.assertEqual(chip["query"], f"service={self.sitting.pk}")

    def test_no_chips_when_nobody_is_found(self):
        response = self.client.get(URL, {"area": "BX0803", "distance": "1"})
        self.assertEqual(self.names(response), [])
        self.assertNotContains(response, 'class="service-filters"')

    def test_chips_stay_when_a_filter_finds_nobody(self):
        response = self.client.get(
            URL, {"area": "MN0202", "service": self.sitting.pk, "distance": "1"}
        )
        self.assertEqual(self.names(response), [])
        self.assertContains(response, 'class="service-filters"')
        self.assertContains(response, "Clear filter")

    def test_sort_menu_sits_in_the_results_heading(self):
        response = self.client.get(URL, {"location": "x", **NYU, "sort": "experience"})
        self.assertContains(
            response,
            '<option value="experience" selected>Most experienced</option>',
            html=True,
        )
        # Sorting keeps the search; the sort form carries it as hidden fields.
        self.assertContains(
            response, '<input type="hidden" name="lat" value="40.729">', html=True
        )

    def test_clearing_the_filter_keeps_the_location(self):
        response = self.client.get(
            URL, {"location": "x", **NYU, "service": self.walking.pk, "distance": "2"}
        )
        query = response.context["query_without_service"]
        self.assertNotIn("service=", query)
        self.assertIn("lat=40.729", query)
        self.assertIn("distance=2", query)

    def test_combines_with_location_search(self):
        response = self.client.get(URL, {"location": "x", **NYU, "service": self.sitting.pk})
        self.assertEqual(self.names(response), ["Alicia", "Marcus"])
        self.assertContains(response, "2 caregivers near")
        points = [p["name"] for p in response.context["map_data"]["points"]]
        self.assertEqual(points, ["Alicia", "Marcus"])

    def test_no_match_message(self):
        response = self.client.get(
            URL, {"area": "MN0202", "service": self.sitting.pk, "distance": "1"}
        )
        self.assertEqual(self.names(response), [])
        self.assertContains(response, "No caregivers offer Pet sitting near")

    def test_unknown_service_is_ignored_with_a_message(self):
        for value in ("999999", "abc"):
            response = self.client.get(URL, {"service": value})
            self.assertContains(response, "Choose a service from the list.")
            self.assertEqual(len(self.names(response)), 5)

    def test_booking_form_preselects_the_service(self):
        response = self.client.get(
            BOOKING_URL, {"caregiver": self.midtown.pk, "service_type": self.sitting.pk}
        )
        form = response.context["form"]
        self.assertEqual(form.initial["caregiver"], str(self.midtown.pk))
        self.assertEqual(form.initial["service_type"], str(self.sitting.pk))


class FilterByAvailabilityTests(FilterTestData):
    """#35: only caregivers taking new bookings are shown (the page has no
    control for it yet; ?availability=any is kept for a future filter)."""

    def test_unavailable_caregivers_are_excluded(self):
        response = self.client.get(URL)
        self.assertNotIn("Busy", self.names(response))
        self.assertNotContains(response, "Not taking new bookings")

    def test_any_availability_includes_them_marked_unavailable(self):
        response = self.client.get(URL, {"availability": "any"})
        self.assertIn("Busy", self.names(response))
        self.assertContains(response, "Not taking new bookings")
        # The choice is kept when the owner searches again.
        self.assertContains(response, '<input type="hidden" name="availability" value="any">')

    def test_available_is_the_default(self):
        available = self.client.get(URL, {"availability": "available"})
        self.assertNotIn("Busy", self.names(available))
        self.assertNotContains(available, 'name="availability" value="any"')

    def test_follows_the_caregiver_setting(self):
        self.busy.accepting_new_bookings = True
        self.busy.save()
        self.assertIn("Busy", self.names(self.client.get(URL)))
        self.village.accepting_new_bookings = False
        self.village.save()
        self.assertNotIn("Chloe", self.names(self.client.get(URL)))

    def test_unknown_value_falls_back_to_available(self):
        response = self.client.get(URL, {"availability": "tomorrow"})
        self.assertNotIn("Busy", self.names(response))
        self.assertEqual(response.context["availability"], "available")

    def test_profiles_without_an_account_stay_hidden(self):
        self.make("NoAccount", "40.730", "-73.996", user=False)
        response = self.client.get(URL, {"availability": "any"})
        self.assertNotIn("NoAccount", self.names(response))

    def test_combines_with_service_and_location(self):
        params = {"location": "x", **NYU, "service": self.walking.pk}
        self.assertEqual(self.names(self.client.get(URL, params)), ["Chloe", "Alicia"])
        self.assertEqual(
            self.names(self.client.get(URL, {**params, "availability": "any"})),
            ["Chloe", "Busy", "Alicia"],
        )

    def test_unavailable_caregiver_still_cannot_be_requested(self):
        response = self.client.post(BOOKING_URL, {"caregiver": self.busy.pk})
        self.assertEqual(
            response.context["form"].errors["caregiver"],
            ["This caregiver isn't taking new bookings."],
        )
