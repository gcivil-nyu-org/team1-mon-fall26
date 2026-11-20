"""Tests for admin pet and service type management."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from caregivers.models import ServiceType
from pets.models import PetType

User = get_user_model()


class ManageTypesTests(TestCase):
    """Test admin management of pet and service types."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="testadmin",
            email="admin@example.com",
            password="TestPassword123!",
        )

        self.regular_user = User.objects.create_user(
            username="testuser",
            email="user@example.com",
            password="TestPassword123!",
        )

        self.manage_url = reverse("staff:manage_types")
        self.add_url = reverse("staff:add_type")
        self.rename_url = reverse("staff:rename_type")

        self.pet_type = PetType.objects.create(name="Test Dog")
        self.service_type = ServiceType.objects.create(name="Test Walking")

    def test_admin_can_view_management_page(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.manage_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Dog")
        self.assertTemplateUsed(
            response,
            "staff/manage_types.html",
        )

    def test_admin_can_view_service_types(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            self.manage_url,
            {"tab": "services"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Walking")

    def test_regular_user_cannot_access_management_page(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(self.manage_url)

        self.assertNotEqual(response.status_code, 200)

    def test_regular_user_cannot_add_type(self):
        self.client.force_login(self.regular_user)

        unique_name = "Unauthorized Test Type 106"

        self.assertFalse(PetType.objects.filter(name=unique_name).exists())

        self.client.post(
            self.add_url,
            {
                "tab": "pets",
                "name": unique_name,
            },
        )

        self.assertFalse(
            PetType.objects.filter(name=unique_name).exists(),
            "A regular user was able to create a pet type!",
        )

    def test_admin_can_add_pet_type(self):
        self.client.force_login(self.admin)

        unique_name = "Test Unique Hamster 106"

        response = self.client.post(
            self.add_url,
            {
                "tab": "pets",
                "name": unique_name,
            },
        )

        new_type = PetType.objects.get(name=unique_name)

        self.assertRedirects(
            response,
            self.manage_url + "?tab=pets&selected=" + str(new_type.pk),
        )

        self.assertTrue(PetType.objects.filter(name=unique_name).exists())

    def test_admin_can_add_service_type(self):
        self.client.force_login(self.admin)

        self.client.post(
            self.add_url,
            {"tab": "services", "name": "Pet Massage"},
        )

        self.assertTrue(ServiceType.objects.filter(name="Pet Massage").exists())

    def test_admin_can_rename_pet_type(self):
        self.client.force_login(self.admin)

        self.client.post(
            self.rename_url,
            {
                "tab": "pets",
                "type_id": self.pet_type.pk,
                "name": "Test Canine",
            },
        )

        self.pet_type.refresh_from_db()
        self.assertEqual(
            self.pet_type.name,
            "Test Canine",
        )

    def test_admin_can_rename_service_type(self):
        self.client.force_login(self.admin)

        unique_name = "Test Unique Walking 106"

        self.client.post(
            self.rename_url,
            {
                "tab": "services",
                "type_id": self.service_type.pk,
                "name": unique_name,
            },
        )

        self.service_type.refresh_from_db()

        self.assertEqual(
            self.service_type.name,
            unique_name,
        )

    def test_duplicate_pet_type_is_rejected(self):
        self.client.force_login(self.admin)

        original_count = PetType.objects.count()

        self.client.post(
            self.add_url,
            {"tab": "pets", "name": "test dog"},
        )

        self.assertEqual(
            PetType.objects.count(),
            original_count,
        )

    def test_duplicate_service_type_is_rejected(self):
        self.client.force_login(self.admin)

        original_count = ServiceType.objects.count()

        self.client.post(
            self.add_url,
            {"tab": "services", "name": "test walking"},
        )

        self.assertEqual(
            ServiceType.objects.count(),
            original_count,
        )

    def test_empty_name_is_rejected(self):
        self.client.force_login(self.admin)

        original_count = PetType.objects.count()

        self.client.post(
            self.add_url,
            {"tab": "pets", "name": "   "},
        )

        self.assertEqual(
            PetType.objects.count(),
            original_count,
        )

    def test_rename_to_duplicate_is_rejected(self):
        self.client.force_login(self.admin)

        other_type = PetType.objects.create(name="Test Cat")

        self.client.post(
            self.rename_url,
            {
                "tab": "pets",
                "type_id": other_type.pk,
                "name": "Test Dog",
            },
        )

        other_type.refresh_from_db()
        self.assertEqual(
            other_type.name,
            "Test Cat",
        )

    def test_get_cannot_add_type(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.add_url)

        self.assertEqual(response.status_code, 405)

    def test_get_cannot_rename_type(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.rename_url)

        self.assertEqual(response.status_code, 405)
