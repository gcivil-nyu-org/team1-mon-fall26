from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile


class HomeRedirectTests(TestCase):
    url = reverse("home")

    def make_user(self, username, role):
        user = User.objects.create_user(username, password="Pawpal!2026x")
        AccountProfile.objects.create(user=user, role=role)
        return user

    def test_logged_out_visitor_goes_to_login(self):
        self.assertRedirects(self.client.get(self.url), reverse("login"))

    def test_pet_owner_goes_to_my_pets(self):
        self.client.force_login(self.make_user("owner", "pet_owner"))
        self.assertRedirects(self.client.get(self.url), reverse("pets:list"))

    def test_caregiver_goes_to_requests(self):
        user = self.make_user("sitter", "caregiver")
        CaregiverProfile.objects.create(
            user=user, name="Chloe Shih", service_area="Brooklyn"
        )
        self.client.force_login(user)
        self.assertRedirects(
            self.client.get(self.url), reverse("bookings:caregiver_requests")
        )

    def test_caregiver_without_profile_goes_to_requests(self):
        # The requests page asks them to create their caregiver profile first.
        self.client.force_login(self.make_user("newsitter", "caregiver"))
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("bookings:caregiver_requests"))

    def test_caregiver_without_profile_gets_caregiver_header(self):
        self.client.force_login(self.make_user("newsitter", "caregiver"))
        response = self.client.get(reverse("bookings:caregiver_requests"))
        self.assertContains(
            response, '<span class="account-role">Caregiver</span>', html=True
        )
        self.assertContains(response, f'href="{reverse("create_caregiver_profile")}"')
        self.assertNotContains(response, ">My pets</a>")

    def test_pet_owner_gets_pet_owner_header(self):
        self.client.force_login(self.make_user("owner", "pet_owner"))
        response = self.client.get(reverse("pets:list"))
        self.assertContains(
            response, '<span class="account-role">Pet owner</span>', html=True
        )
        self.assertContains(response, ">My pets</a>")

    def test_login_lands_on_start_page(self):
        self.make_user("owner", "pet_owner")
        response = self.client.post(
            reverse("login"),
            {"username": "owner", "password": "Pawpal!2026x"},
            follow=True,
        )
        self.assertRedirects(response, reverse("pets:list"))
