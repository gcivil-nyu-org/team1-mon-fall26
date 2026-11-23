"""Pet owner and caregiver pages refuse the other role when opened by URL
(#306, #333, #347)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from accounts.roles import is_caregiver
from pets.models import Pet, PetType

REQUESTS = reverse("bookings:caregiver_requests")


def account(username, role):
    user = get_user_model().objects.create_user(username, password="pw-12345!")
    AccountProfile.objects.create(user=user, role=role)
    return user


class IsCaregiverTests(TestCase):
    def test_roles(self):
        self.assertTrue(is_caregiver(account("cg", AccountProfile.Role.CAREGIVER)))
        self.assertFalse(is_caregiver(account("own", AccountProfile.Role.PET_OWNER)))
        self.assertFalse(is_caregiver(get_user_model().objects.create_user("plain")))


class OwnerCannotBecomeCaregiverTests(TestCase):
    def test_owner_is_sent_home(self):
        owner = account("owner", AccountProfile.Role.PET_OWNER)
        self.client.force_login(owner)
        for method in (self.client.get, self.client.post):
            response = method(reverse("create_caregiver_profile"))
            self.assertRedirects(
                response, reverse("home"), fetch_redirect_response=False
            )
        self.assertFalse(hasattr(owner, "caregiver_profile"))

    def test_caregiver_account_sees_the_form(self):
        self.client.force_login(account("cg", AccountProfile.Role.CAREGIVER))
        response = self.client.get(reverse("create_caregiver_profile"))
        self.assertEqual(response.status_code, 200)


class CaregiverCannotUseOwnerPagesTests(TestCase):
    def setUp(self):
        self.caregiver = account("cg", AccountProfile.Role.CAREGIVER)
        self.client.force_login(self.caregiver)

    def test_owner_pages_send_caregivers_to_their_requests(self):
        for name in (
            "pets:list",
            "pets:create",
            "bookings:booking_list",
            "bookings:booking_create",
            "opportunities:list",
            "opportunities:create",
        ):
            with self.subTest(name):
                response = self.client.get(reverse(name))
                self.assertRedirects(response, REQUESTS, fetch_redirect_response=False)

    def test_caregiver_cannot_create_a_pet(self):
        dog = PetType.objects.get_or_create(name="Dog")[0]
        self.client.post(
            reverse("pets:create"), {"name": "QA CG Pet", "pet_type": dog.pk}
        )
        self.assertFalse(Pet.objects.exists())

    def test_owner_still_gets_owner_pages(self):
        self.client.force_login(account("owner", AccountProfile.Role.PET_OWNER))
        for name in ("pets:list", "pets:create", "bookings:booking_list"):
            with self.subTest(name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
