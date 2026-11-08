"""A pet owner's neighborhood, shown to the caregivers they message."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.deletion import delete_account
from accounts.models import AccountProfile

User = get_user_model()
URL = reverse("neighborhood")


class NeighborhoodTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("kat")
        self.profile = AccountProfile.objects.create(user=self.owner)

    def test_owner_can_save_a_neighborhood(self):
        self.client.force_login(self.owner)
        response = self.client.post(URL, {"neighborhood": "Park Slope"}, follow=True)
        self.assertContains(response, "Your neighborhood is saved.")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.neighborhood, "Park Slope")

    def test_owner_sees_the_link_in_the_account_menu(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(URL), f'href="{URL}"')

    def test_caregiver_is_sent_home(self):
        sitter = User.objects.create_user("chloe")
        AccountProfile.objects.create(user=sitter, role=AccountProfile.Role.CAREGIVER)
        self.client.force_login(sitter)
        self.assertRedirects(
            self.client.post(URL, {"neighborhood": "Gowanus"}),
            reverse("home"),
            fetch_redirect_response=False,
        )

    def test_login_is_required(self):
        self.assertEqual(self.client.get(URL).status_code, 302)

    def test_deleting_the_account_clears_it(self):
        self.profile.neighborhood = "Park Slope"
        self.profile.save()
        delete_account(self.owner)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.neighborhood, "")
