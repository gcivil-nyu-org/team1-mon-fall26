"""Figma "Explore" section: caregivers find pets needing care under Explore,
with the same Location and Distance search as the other Explore pages, and
pet owners filter caregivers by pet and service."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile, CaregiverService, ServiceType
from caregivers.search import find_neighborhood
from opportunities.models import CareOpportunity
from pets.models import Pet, PetType

User = get_user_model()
BROWSE_URL = reverse("opportunities:browse")
PLACES_URL = reverse("places:explore")
CAREGIVERS_URL = reverse("caregiver_list")


class ExploreTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dog = PetType.objects.get_or_create(name="Dog")[0]
        cls.cat = PetType.objects.get_or_create(name="Cat")[0]
        cls.walking = ServiceType.objects.get_or_create(name="Dog walking")[0]
        cls.feeding = ServiceType.objects.get_or_create(name="Feeding")[0]

        cls.owner = User.objects.create_user(
            "kat", password="pw-12345!", first_name="Kat", last_name="W"
        )
        AccountProfile.objects.create(user=cls.owner, neighborhood="Park Slope")

        cls.sitter = User.objects.create_user(
            "chloe", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        AccountProfile.objects.create(
            user=cls.sitter, role=AccountProfile.Role.CAREGIVER
        )
        slope = find_neighborhood("Park Slope")
        cls.caregiver = CaregiverProfile.objects.create(
            user=cls.sitter,
            name="Chloe Shih",
            service_area="Park Slope",
            neighborhood="Park Slope",
            latitude=slope["latitude"],
            longitude=slope["longitude"],
        )
        cls.caregiver.supported_pet_types.set([cls.dog])
        CaregiverService.objects.create(
            caregiver=cls.caregiver, service_type=cls.walking, price=Decimal("25")
        )

        cls.nearby = cls.post("Biscuit", cls.dog, cls.walking, "Park Slope, Brooklyn")
        cls.far = cls.post("Miso", cls.cat, cls.feeding, "Astoria (Central), Queens")

    @classmethod
    def post(cls, name, pet_type, service, location):
        pet = Pet.objects.create(owner=cls.owner, name=name, pet_type=pet_type)
        start = timezone.now() + timedelta(days=2)
        return CareOpportunity.objects.create(
            owner=cls.owner,
            pet=pet,
            service_type=service,
            start_time=start,
            end_time=start + timedelta(hours=1),
            location=location,
        )


class CaregiverExploreTests(ExploreTestData):
    def setUp(self):
        self.client.force_login(self.sitter)

    def test_find_pets_is_under_explore_in_the_menu(self):
        response = self.client.get(BROWSE_URL)
        self.assertNotContains(response, ">Find pets</a>")
        self.assertContains(
            response, f'<a href="{BROWSE_URL}" class="active">Explore</a>', html=True
        )

    def test_explore_opens_on_pets_needing_care(self):
        response = self.client.get(PLACES_URL)
        self.assertContains(
            response, f'<a href="{BROWSE_URL}" class="active">Explore</a>', html=True
        )

    def test_without_a_profile_explore_opens_on_places(self):
        new = User.objects.create_user("newsitter", password="pw-12345!")
        AccountProfile.objects.create(user=new, role=AccountProfile.Role.CAREGIVER)
        self.client.force_login(new)
        response = self.client.get(PLACES_URL)
        self.assertContains(
            response, f'<a href="{PLACES_URL}" class="active">Explore</a>', html=True
        )

    def test_looking_for_pets_needing_care(self):
        for url in (BROWSE_URL, PLACES_URL):
            response = self.client.get(url)
            self.assertContains(response, "Pets needing care")
            self.assertNotContains(response, '<option value="caregivers"')

    def test_switching_looking_for_keeps_the_search(self):
        query = {"location": "Park Slope", "distance": "2"}
        response = self.client.get(PLACES_URL, {"looking_for": "pets", **query})
        self.assertRedirects(response, f"{BROWSE_URL}?location=Park+Slope&distance=2")
        response = self.client.get(BROWSE_URL, {"looking_for": "places", **query})
        self.assertRedirects(
            response,
            f"{PLACES_URL}?location=Park+Slope&distance=2",
            fetch_redirect_response=False,
        )
        response = self.client.get(BROWSE_URL, {"looking_for": "caregivers"})
        self.assertRedirects(response, CAREGIVERS_URL, fetch_redirect_response=False)
        response = self.client.get(CAREGIVERS_URL, {"looking_for": "pets"})
        self.assertRedirects(response, BROWSE_URL)

    def test_before_a_search_posts_within_the_distance_of_the_caregivers_area(self):
        # The list matches the distance shown in the search bar (#299).
        response = self.client.get(BROWSE_URL)
        self.assertEqual(response.context["posts"], [self.nearby])
        self.assertContains(response, "1 open near you")
        self.assertContains(response, 'value="Park Slope"')
        self.assertContains(response, "Enter a neighborhood or ZIP code to see pets")
        self.assertEqual(response.context["posts"][0].distance, 0.0)

    def test_search_shows_posts_within_the_distance(self):
        response = self.client.get(
            BROWSE_URL, {"location": "Park Slope", "distance": "1"}
        )
        self.assertEqual(response.context["posts"], [self.nearby])
        self.assertContains(response, "1 open near Park Slope")
        response = self.client.get(BROWSE_URL, {"location": "Astoria", "distance": "1"})
        self.assertEqual(response.context["posts"], [self.far])

    def test_search_with_nothing_nearby(self):
        response = self.client.get(
            BROWSE_URL, {"location": "Upper East Side", "distance": "1"}
        )
        self.assertEqual(response.context["posts"], [])
        self.assertContains(response, "No pets need care near Upper East Side yet")
        self.assertContains(response, "Try a larger distance or another neighborhood.")

    def test_use_my_current_location(self):
        slope = find_neighborhood("Park Slope")
        response = self.client.get(
            BROWSE_URL,
            {
                "here": "1",
                "lat": f"{slope['latitude']:.3f}",
                "lng": f"{slope['longitude']:.3f}",
                "distance": "1",
            },
        )
        self.assertEqual(response.context["posts"], [self.nearby])
        self.assertContains(response, "1 open near you (Park Slope)")
        self.assertEqual(response.context["location_text"], "")

    def test_location_outside_nyc_says_so(self):
        response = self.client.get(BROWSE_URL, {"here": "1", "lat": "1", "lng": "1"})
        self.assertFalse(response.context["searched"])
        self.assertContains(response, "isn&#x27;t in New York City")
        self.assertEqual(response.context["location_text"], "")

    def test_filters_keep_the_search_and_have_no_clear_link(self):
        response = self.client.get(
            BROWSE_URL,
            {"location": "Park Slope", "distance": "5", "service": self.walking.pk},
        )
        self.assertNotContains(response, "co-filter-clear")
        cat = next(i for i in response.context["pet_filters"] if i["label"] == "Cat")
        self.assertEqual(
            cat["query"],
            f"location=Park+Slope&distance=5&service={self.walking.pk}&pet_type={self.cat.pk}",
        )
        self.assertEqual(
            response.context["clear_filters_query"], "location=Park+Slope&distance=5"
        )
        self.assertContains(response, f'name="service" value="{self.walking.pk}"')

    def test_no_match_for_a_filter(self):
        response = self.client.get(
            BROWSE_URL, {"pet_type": self.cat.pk, "service": self.walking.pk}
        )
        self.assertContains(response, "No pets match yet")
        self.assertContains(response, 'href="?">Clear filters</a>')

    def test_caregiver_without_a_location(self):
        CaregiverProfile.objects.filter(pk=self.caregiver.pk).update(
            latitude=None, longitude=None
        )
        response = self.client.get(BROWSE_URL)
        self.assertEqual(len(response.context["posts"]), 2)
        self.assertIsNone(response.context["posts"][0].distance)


class OwnerExploreTests(ExploreTestData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_starts_from_the_owners_neighborhood(self):
        response = self.client.get(CAREGIVERS_URL)
        self.assertContains(response, "1 caregiver near Park Slope")
        self.assertContains(response, 'value="Park Slope"')
        # Clearing the Location box searches all of PawPal again.
        response = self.client.get(CAREGIVERS_URL, {"location": ""})
        self.assertContains(response, "1 caregiver on PawPal")

    def test_looking_for_caregivers(self):
        response = self.client.get(PLACES_URL)
        self.assertContains(response, '<option value="caregivers"')
        self.assertNotContains(response, "Pets needing care")

    def test_filter_by_pet(self):
        response = self.client.get(
            CAREGIVERS_URL, {"location": "", "pet_type": self.dog.pk}
        )
        self.assertEqual(
            [c.name for c in response.context["caregivers"]], ["Chloe Shih"]
        )
        self.assertContains(response, '<span class="co-filter-value">Dog</span>')
        self.assertContains(response, 'name="pet_type"')
        response = self.client.get(
            CAREGIVERS_URL, {"location": "", "pet_type": self.cat.pk}
        )
        self.assertEqual(response.context["caregivers"], [])

    def test_unknown_pet_type(self):
        response = self.client.get(CAREGIVERS_URL, {"location": "", "pet_type": "999"})
        self.assertContains(response, "Choose a pet from the list.")
        self.assertEqual(len(response.context["caregivers"]), 1)
