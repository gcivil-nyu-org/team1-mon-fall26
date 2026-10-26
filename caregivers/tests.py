from decimal import Decimal
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from pets.models import PetType

from .forms import CaregiverProfileForm, CaregiverServicesForm
from .geocoding import Location
from .models import CaregiverProfile, CaregiverService, ServiceType

WASHINGTON_SQUARE = Location(
    latitude=Decimal("40.729"),
    longitude=Decimal("-73.997"),
    neighborhood="Greenwich Village",
    borough="Manhattan",
)


class CaregiverTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dog = PetType.objects.get_or_create(name="Dog")[0]
        cls.cat = PetType.objects.get_or_create(name="Cat")[0]
        cls.walking = ServiceType.objects.get_or_create(name="Dog walking")[0]
        cls.sitting = ServiceType.objects.get_or_create(name="Pet sitting")[0]

        cls.user = get_user_model().objects.create_user(
            username="caregiver_test",
            password="TestPassword123!"
        )

    def setUp(self):
        # Never call the real GeoSearch service from tests.
        patcher = mock.patch(
            "caregivers.forms.geocode", return_value=WASHINGTON_SQUARE
        )
        self.geocode = patcher.start()
        self.addCleanup(patcher.stop)

    def profile_data(self, **overrides):
        data = {
            "first_name": "Chloe",
            "last_name": "Shih",
            "bio": "Lifelong dog person.",
            "years_of_experience": 4,
            "address": "70 Washington Square South",
            "service_radius_miles": 3,
            "special_skills": "Giving medication",
            "certifications": "Pet First Aid",
            "supported_pet_types": [self.dog.pk, self.cat.pk],
            "accepting_new_bookings": "on",
            "selected_services": [self.walking.pk],
        }
        data.update(overrides)
        return data

    def make_caregiver(self, **fields):
        defaults = {"name": "Chloe Shih", "service_area": "Brooklyn"}
        defaults.update(fields)
        return CaregiverProfile.objects.create(**defaults)

    def make_service(self, caregiver, service_type=None, **fields):
        defaults = {
            "caregiver": caregiver,
            "service_type": service_type or self.walking,
            "price": Decimal("25.00"),
            "price_unit": "walk",
            "is_active": True,
        }
        defaults.update(fields)
        return CaregiverService.objects.create(**defaults)

    def service_data(self, **overrides):
        data = {
            "service_type": self.walking.pk,
            "price_unit": "walk",
            "price": "25.00",
            "description": "30 minute walk",
            "is_active": "on",
        }
        data.update(overrides)
        return data


class CaregiverModelTests(CaregiverTestData):
    def test_new_profile_defaults(self):
        caregiver = self.make_caregiver()
        self.assertTrue(caregiver.accepting_new_bookings)
        self.assertEqual(caregiver.years_of_experience, 0)

    def test_service_type_str_is_its_name(self):
        self.assertEqual(str(self.walking), "Dog walking")

    def test_caregiver_cannot_list_the_same_service_twice(self):
        caregiver = self.make_caregiver()
        self.make_service(caregiver)
        with self.assertRaises(IntegrityError):
            self.make_service(caregiver)


class CaregiverProfileFormTests(CaregiverTestData):
    def test_valid_profile(self):
        form = CaregiverProfileForm(data=self.profile_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_first_and_last_name_are_required(self):
        form = CaregiverProfileForm(data=self.profile_data(first_name="", last_name=""))
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)
        self.assertIn("last_name", form.errors)

    def test_edit_form_splits_the_saved_name(self):
        caregiver = CaregiverProfile.objects.create(name="Chloe Ann Shih", service_area="Brooklyn")
        form = CaregiverProfileForm(instance=caregiver)
        self.assertEqual(form.initial["first_name"], "Chloe")
        self.assertEqual(form.initial["last_name"], "Ann Shih")

    def test_years_of_experience_cannot_be_negative(self):
        form = CaregiverProfileForm(data=self.profile_data(years_of_experience=-1))
        self.assertFalse(form.is_valid())
        self.assertIn("years_of_experience", form.errors)

    def test_services_and_pet_types_are_optional(self):
        form = CaregiverProfileForm(
            data=self.profile_data(selected_services=[], supported_pet_types=[])
        )
        self.assertTrue(form.is_valid(), form.errors)


class CreateCaregiverProfileViewTests(CaregiverTestData):
    url = reverse("create_caregiver_profile")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_get_shows_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dog walking")

    def test_pet_care_skills_are_saved(self):
        self.client.post(
            self.url,
            self.profile_data(pet_care_skills=["giving_medication", "leash_training"]),
        )
        caregiver = CaregiverProfile.objects.get()
        self.assertEqual(caregiver.pet_care_skills, ["giving_medication", "leash_training"])
        self.assertEqual(
            caregiver.pet_care_skill_labels, ["Giving medication", "Leash training"]
        )

    def test_form_shows_years_as_ranges(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<option value="3">3–5 years</option>', html=True)
        self.assertContains(response, "Pet-care skills")

    def test_post_saves_profile_and_redirects_to_it(self):
        response = self.client.post(self.url, self.profile_data())
        caregiver = CaregiverProfile.objects.get()
        self.assertRedirects(response, reverse("caregiver", args=[caregiver.pk]))
        self.assertEqual(caregiver.name, "Chloe Shih")
        # The neighborhood comes from GeoSearch, not from the caregiver.
        self.assertEqual(caregiver.service_area, "Greenwich Village, Manhattan")
        # 4 years is saved as the start of its range, "3–5 years".
        self.assertEqual(caregiver.years_of_experience, 3)
        self.assertEqual(caregiver.experience_label, "3–5 years")
        self.assertEqual(caregiver.special_skills, "Giving medication")
        self.assertTrue(caregiver.accepting_new_bookings)
        self.assertEqual(
            set(caregiver.supported_pet_types.all()), {self.dog, self.cat}
        )

    def test_selected_services_are_offered_right_away(self):
        self.client.post(
            self.url, self.profile_data(selected_services=[self.walking.pk, self.sitting.pk])
        )
        services = CaregiverService.objects.filter(caregiver__name="Chloe Shih")
        self.assertEqual(
            set(services.values_list("service_type__name", flat=True)),
            {"Dog walking", "Pet sitting"},
        )
        # Offered (shown in search and booking) without needing a price.
        self.assertEqual(services.filter(is_active=True).count(), 2)
        self.assertFalse(services.filter(price__isnull=False).exists())

    def test_invalid_post_saves_nothing(self):
        response = self.client.post(self.url, self.profile_data(first_name=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CaregiverProfile.objects.exists())


class CaregiverProfileDetailViewTests(CaregiverTestData):
    def test_public_profile_shows_profile_information(self):
        caregiver = self.make_caregiver(
            bio="Lifelong dog person.", years_of_experience=4
        )
        caregiver.supported_pet_types.set([self.dog])
        response = self.client.get(reverse("caregiver", args=[caregiver.pk]))
        self.assertContains(response, "Chloe Shih")
        self.assertContains(response, "Brooklyn")
        self.assertContains(response, "Lifelong dog person.")
        # 4 years shows as its range.
        self.assertContains(response, "3–5 years caring for pets")
        self.assertContains(response, "Dog")

    def test_only_offered_services_are_listed(self):
        caregiver = self.make_caregiver()
        self.make_service(caregiver, self.walking, price=Decimal("25.00"))
        self.make_service(caregiver, self.sitting, price=None, is_active=False)
        response = self.client.get(reverse("caregiver", args=[caregiver.pk]))
        # Prices are hidden on the profile for now.
        self.assertNotContains(response, "$25.00")
        # Switched-off services don't show under "Services".
        self.assertEqual(
            [s.service_type for s in response.context["provided_services"]], [self.walking]
        )

    def test_profile_shows_skills_and_first_name(self):
        caregiver = self.make_caregiver(pet_care_skills=["leash_training"])
        response = self.client.get(reverse("caregiver", args=[caregiver.pk]))
        self.assertContains(response, "Leash training")
        self.assertContains(response, "Request care from Chloe")
        self.assertContains(response, "CS")

    def test_own_profile_hides_the_request_card(self):
        caregiver = self.make_caregiver(user=self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("caregiver", args=[caregiver.pk]))
        self.assertNotContains(response, "Request care from")
        self.assertContains(response, "Edit profile")

    def test_missing_profile_returns_404(self):
        response = self.client.get(reverse("caregiver", args=[999]))
        self.assertEqual(response.status_code, 404)


class EditCaregiverProfileViewTests(CaregiverTestData):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_edit_form_is_prefilled(self):
        caregiver = self.make_caregiver(user=self.user)
        self.make_service(caregiver)
        response = self.client.get(reverse("edit_caregiver_profile", args=[caregiver.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.instance, caregiver)
        self.assertIn(self.walking.pk, list(form.initial["selected_services"]))

    def test_unpicked_services_are_switched_off_and_repicked_ones_back_on(self):
        caregiver = self.make_caregiver(user=self.user)
        walk = self.make_service(caregiver, self.walking, price=Decimal("25.00"))
        url = reverse("edit_caregiver_profile", args=[caregiver.pk])
        self.client.post(url, self.profile_data(selected_services=[self.sitting.pk]))
        walk.refresh_from_db()
        self.assertFalse(walk.is_active)
        # Its price is kept for when it's picked again.
        self.assertEqual(walk.price, Decimal("25.00"))
        self.assertTrue(
            CaregiverService.objects.get(caregiver=caregiver, service_type=self.sitting).is_active
        )
        self.client.post(url, self.profile_data(selected_services=[self.walking.pk]))
        walk.refresh_from_db()
        self.assertTrue(walk.is_active)

    def test_post_updates_profile(self):
        caregiver = self.make_caregiver(user=self.user)
        response = self.client.post(
            reverse("edit_caregiver_profile", args=[caregiver.pk]),
            self.profile_data(first_name="Dana", last_name="Ruiz", accepting_new_bookings=""),
        )
        self.assertRedirects(response, reverse("caregiver", args=[caregiver.pk]))
        caregiver.refresh_from_db()
        self.assertEqual(caregiver.name, "Dana Ruiz")
        self.assertEqual(caregiver.service_area, "Greenwich Village, Manhattan")
        self.assertFalse(caregiver.accepting_new_bookings)


class CaregiverServiceViewTests(CaregiverTestData):
    def setUp(self):
        super().setUp()
        self.caregiver = self.make_caregiver(user=self.user)
        self.client.force_login(self.user)

    def test_list_shows_caregivers_services_only(self):
        self.make_service(self.caregiver, description="30 minute walk")
        other = self.make_caregiver(name="Alicia Tian")
        self.make_service(other, self.sitting, description="Overnight stay")
        response = self.client.get(reverse("services", args=[self.caregiver.pk]))
        self.assertContains(response, "30 minute walk")
        self.assertNotContains(response, "Overnight stay")

    def test_add_and_edit_service_pages_load(self):
        service = self.make_service(self.caregiver)
        add = self.client.get(reverse("add_caregiver_service", args=[self.caregiver.pk]))
        self.assertEqual(add.status_code, 200)
        edit = self.client.get(
            reverse("edit_caregiver_service", args=[self.caregiver.pk, service.pk])
        )
        self.assertEqual(edit.status_code, 200)
        self.assertEqual(edit.context["form"].instance, service)

    def test_add_service(self):
        response = self.client.post(
            reverse("add_caregiver_service", args=[self.caregiver.pk]),
            self.service_data(),
        )
        self.assertRedirects(response, reverse("services", args=[self.caregiver.pk]))
        service = CaregiverService.objects.get(caregiver=self.caregiver)
        self.assertEqual(service.service_type, self.walking)
        self.assertEqual(service.price, Decimal("25.00"))
        self.assertTrue(service.is_active)

    def test_cannot_add_the_same_service_twice(self):
        self.make_service(self.caregiver)
        response = self.client.post(
            reverse("add_caregiver_service", args=[self.caregiver.pk]),
            self.service_data(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("service_type", response.context["form"].errors)
        self.assertEqual(CaregiverService.objects.filter(caregiver=self.caregiver).count(), 1)

    def test_price_cannot_have_too_many_digits(self):
        form = CaregiverServicesForm(data=self.service_data(price="1234567.00"))
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_edit_service(self):
        service = self.make_service(self.caregiver)
        response = self.client.post(
            reverse("edit_caregiver_service", args=[self.caregiver.pk, service.pk]),
            self.service_data(price="30.00", price_unit="hour", is_active=""),
        )
        self.assertRedirects(response, reverse("services", args=[self.caregiver.pk]))
        service.refresh_from_db()
        self.assertEqual(service.price, Decimal("30.00"))
        self.assertEqual(service.price_unit, "hour")
        self.assertFalse(service.is_active)

    def test_delete_service_asks_for_confirmation_first(self):
        service = self.make_service(self.caregiver)
        url = reverse("delete_caregiver_service", args=[self.caregiver.pk, service.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(CaregiverService.objects.filter(pk=service.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, reverse("services", args=[self.caregiver.pk]))
        self.assertFalse(CaregiverService.objects.filter(pk=service.pk).exists())

    def test_cannot_change_another_caregivers_service_through_the_wrong_url(self):
        other = self.make_caregiver(name="Alicia Tian")
        service = self.make_service(other)
        url = reverse("delete_caregiver_service", args=[self.caregiver.pk, service.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(CaregiverService.objects.filter(pk=service.pk).exists())
