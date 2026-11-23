"""Small fixes other teams found at the testing party: the empty location pin
and the Edit profile title (#305), the chat banner on the caregiver's side
(#337) and avatar initials after a name change (#321)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from messaging.models import Conversation

from .profile_choices import required_choices
from .test_caregivers import WASHINGTON_SQUARE

User = get_user_model()


class SmallUiTests(TestCase):
    def setUp(self):
        patcher = mock.patch("caregivers.forms.geocode", return_value=WASHINGTON_SQUARE)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sitter = User.objects.create_user(
            "cg", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        AccountProfile.objects.create(
            user=self.sitter, role=AccountProfile.Role.CAREGIVER
        )
        self.caregiver = CaregiverProfile.objects.create(
            user=self.sitter, name="Chloe Shih"
        )
        self.owner = User.objects.create_user("kat", first_name="Kat")

    def test_no_pin_without_a_place(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("caregiver_list"))
        self.assertIn(self.caregiver, response.context["caregivers"])
        self.assertNotContains(response, 'class="result-place"')

    def test_edit_page_title(self):
        self.client.force_login(self.sitter)
        response = self.client.get(
            reverse("edit_caregiver_profile", args=[self.caregiver.pk])
        )
        self.assertContains(response, "<title>Edit Caregiver Profile | PawPal")

    def test_name_change_updates_the_account(self):
        self.client.force_login(self.sitter)
        self.client.post(
            reverse("edit_caregiver_profile", args=[self.caregiver.pk]),
            {
                "first_name": "Jax",
                "last_name": "Tran",
                "years_of_experience": 2,
                "address": "70 Washington Square South",
                "service_radius_miles": 3,
                **required_choices(),
            },
        )
        self.sitter.refresh_from_db()
        self.assertEqual(
            (self.sitter.first_name, self.sitter.last_name), ("Jax", "Tran")
        )
        response = self.client.get(reverse("forum:list"))
        self.assertContains(response, ">JT</span>")

    def test_caregiver_side_chat_banner(self):
        conversation = Conversation.objects.create(
            owner=self.owner, caregiver=self.caregiver
        )
        self.client.force_login(self.sitter)
        response = self.client.get(conversation.get_absolute_url())
        self.assertContains(response, "No booking request from Kat yet.")
        self.assertNotContains(response, "is asking questions")
