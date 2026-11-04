"""Tests for the pet-owner Care Opportunities workflow."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.models import CaregiverProfile, ServiceType
from pets.models import Pet, PetType

from opportunities.forms import CareOpportunityForm
from opportunities.models import CareOpportunity


class CareOpportunityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(
            username="post_owner", password="test-pass-123"
        )
        cls.other_user = User.objects.create_user(
            username="other_owner", password="test-pass-123"
        )
        cls.caregiver_user = User.objects.create_user(
            username="caregiver_user", password="test-pass-123"
        )
        cls.pet_type = PetType.objects.get_or_create(name="Rabbit")[0]
        cls.service = ServiceType.objects.get_or_create(name="Feeding")[0]
        cls.other_service = ServiceType.objects.get_or_create(name="Walking")[0]
        cls.pet = Pet.objects.create(
            owner=cls.owner, name="Pepper", pet_type=cls.pet_type
        )
        cls.other_pet = Pet.objects.create(
            owner=cls.other_user, name="Mochi", pet_type=cls.pet_type
        )
        cls.caregiver_profile = CaregiverProfile.objects.create(
            user=cls.caregiver_user,
            name="Caregiver Test",
            service_area="Brooklyn",
        )

    def setUp(self):
        self.start = timezone.now() + timedelta(days=5)
        self.end = self.start + timedelta(hours=2)
        self.opportunity = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=self.service,
            start_time=self.start,
            end_time=self.end,
            location="Park Slope",
            notes="Gentle handling, please.",
        )

    def form_data(self, *, pet=None, start=None, end=None, **overrides):
        start = start or self.start
        end = end or self.end
        data = {
            "pet": self.pet.pk if pet is None else pet.pk,
            "service_type": self.service.pk,
            "location": "Brooklyn",
            "notes": "Please feed at 8 AM.",
            "start_date": timezone.localtime(start).date().isoformat(),
            "start_clock": timezone.localtime(start).strftime("%H:%M"),
            "end_date": timezone.localtime(end).date().isoformat(),
            "end_clock": timezone.localtime(end).strftime("%H:%M"),
        }
        data.update(overrides)
        return data

    def test_default_status_and_ordering(self):
        self.assertEqual(self.opportunity.status, CareOpportunity.Status.OPEN)
        self.assertIn("Care Opportunity", str(self.opportunity))
        later = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=self.service,
            start_time=self.start + timedelta(days=1),
            end_time=self.end + timedelta(days=1),
            location="Queens",
        )
        self.assertEqual(CareOpportunity.objects.first(), later)

    def test_form_accepts_valid_future_dates_and_saves(self):
        form = CareOpportunityForm(data=self.form_data(), owner=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        self.assertIsNone(saved.pk)
        saved.owner = self.owner
        saved.save()
        self.assertEqual(saved.pet, self.pet)
        self.assertGreater(saved.end_time, saved.start_time)

    def test_form_rejects_end_before_start(self):
        form = CareOpportunityForm(
            data=self.form_data(end=self.start - timedelta(hours=1)),
            owner=self.owner,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("End date and time", str(form.non_field_errors()))

    def test_form_rejects_start_in_past(self):
        past = timezone.now() - timedelta(days=2)
        form = CareOpportunityForm(
            data=self.form_data(start=past, end=past + timedelta(hours=1)),
            owner=self.owner,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("future", str(form.non_field_errors()))

    def test_form_rejects_missing_time(self):
        form = CareOpportunityForm(
            data=self.form_data(start_clock=""), owner=self.owner
        )
        self.assertFalse(form.is_valid())
        self.assertIn("start_clock", form.errors)

    def test_form_restricts_pet_to_owner(self):
        form = CareOpportunityForm(
            data=self.form_data(pet=self.other_pet), owner=self.owner
        )
        self.assertFalse(form.is_valid())
        self.assertIn("pet", form.errors)

    def test_form_excludes_soft_deleted_pets(self):
        self.pet.deleted_at = timezone.now()
        self.pet.save(update_fields=["deleted_at"])
        form = CareOpportunityForm(owner=self.owner)
        self.assertNotIn(self.pet, form.fields["pet"].queryset)

    def test_edit_form_locks_pet_and_prefills_dates(self):
        form = CareOpportunityForm(
            instance=self.opportunity, owner=self.owner, lock_pet=True
        )
        self.assertTrue(form.fields["pet"].disabled)
        self.assertEqual(
            form.initial["start_date"], timezone.localtime(self.start).date()
        )
        self.assertEqual(form.initial["end_date"], timezone.localtime(self.end).date())

    def test_edit_form_keeps_soft_deleted_original_pet(self):
        self.pet.deleted_at = timezone.now()
        self.pet.save(update_fields=["deleted_at"])
        form = CareOpportunityForm(
            instance=self.opportunity, owner=self.owner, lock_pet=True
        )
        self.assertIn(self.pet, form.fields["pet"].queryset)

    def test_login_required_for_owner_pages(self):
        urls = [
            reverse("opportunities:list"),
            reverse("opportunities:create"),
            reverse("opportunities:created", args=[self.opportunity.pk]),
            reverse("opportunities:edit", args=[self.opportunity.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("next=", response.url)

    def test_owner_list_shows_only_own_posts(self):
        CareOpportunity.objects.create(
            owner=self.other_user,
            pet=self.other_pet,
            service_type=self.service,
            start_time=self.start,
            end_time=self.end,
            location="Elsewhere",
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["open_posts"]), 1)
        self.assertEqual(response.context["selected"], self.opportunity)

    def test_owner_list_selects_requested_post(self):
        second = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=self.service,
            start_time=self.start + timedelta(days=1),
            end_time=self.end + timedelta(days=1),
            location="Queens",
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("opportunities:list"), {"post": self.opportunity.pk}
        )
        self.assertEqual(response.context["selected"], self.opportunity)
        response = self.client.get(reverse("opportunities:list"), {"post": second.pk})
        self.assertEqual(response.context["selected"], second)

    def test_owner_can_view_creation_form(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:create"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], CareOpportunityForm)

    def test_owner_can_create_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("opportunities:create"), self.form_data())
        self.assertEqual(response.status_code, 302)
        created = CareOpportunity.objects.exclude(pk=self.opportunity.pk).get()
        self.assertEqual(created.owner, self.owner)
        self.assertEqual(created.location, "Brooklyn")
        self.assertEqual(
            response.url, reverse("opportunities:created", args=[created.pk])
        )

    def test_invalid_creation_does_not_save(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("opportunities:create"), self.form_data(location="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CareOpportunity.objects.count(), 1)
        self.assertIn("location", response.context["form"].errors)

    def test_caregiver_cannot_create_post(self):
        self.client.force_login(self.caregiver_user)
        response = self.client.get(reverse("opportunities:create"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("bookings:caregiver_requests"))

    def test_only_owner_can_view_confirmation(self):
        url = reverse("opportunities:created", args=[self.opportunity.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_edit_get_redirects_to_inline_form(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("opportunities:edit", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("edit=1", response.url)
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["editing"])

    def test_owner_can_edit_post(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("opportunities:edit", args=[self.opportunity.pk]),
            self.form_data(location="New location", service_type=self.other_service.pk),
        )
        self.assertEqual(response.status_code, 302)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.location, "New location")
        self.assertEqual(self.opportunity.service_type, self.other_service)
        self.assertEqual(self.opportunity.pet, self.pet)

    def test_invalid_edit_shows_form_and_keeps_old_values(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("opportunities:edit", args=[self.opportunity.pk]),
            self.form_data(location=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["editing"])
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.location, "Park Slope")

    def test_other_user_cannot_edit(self):
        self.client.force_login(self.other_user)
        url = reverse("opportunities:edit", args=[self.opportunity.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.form_data()).status_code, 404)

    def test_owner_can_close_and_reopen(self):
        self.client.force_login(self.owner)
        close_url = reverse("opportunities:close", args=[self.opportunity.pk])
        reopen_url = reverse("opportunities:reopen", args=[self.opportunity.pk])
        self.assertEqual(self.client.post(close_url).status_code, 302)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.status, CareOpportunity.Status.CLOSED)
        response = self.client.get(reverse("opportunities:list"))
        self.assertEqual(len(response.context["closed_posts"]), 1)
        self.assertEqual(self.client.post(reopen_url).status_code, 302)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.status, CareOpportunity.Status.OPEN)

    def test_close_and_reopen_are_post_only(self):
        self.client.force_login(self.owner)
        for name in ("close", "reopen"):
            with self.subTest(name=name):
                response = self.client.get(
                    reverse(f"opportunities:{name}", args=[self.opportunity.pk])
                )
                self.assertEqual(response.status_code, 405)

    def test_other_user_cannot_close_or_reopen(self):
        self.client.force_login(self.other_user)
        for name in ("close", "reopen"):
            with self.subTest(name=name):
                response = self.client.post(
                    reverse(f"opportunities:{name}", args=[self.opportunity.pk])
                )
                self.assertEqual(response.status_code, 404)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.status, CareOpportunity.Status.OPEN)

    def test_repeated_close_and_reopen_are_safe(self):
        self.client.force_login(self.owner)
        close_url = reverse("opportunities:close", args=[self.opportunity.pk])
        reopen_url = reverse("opportunities:reopen", args=[self.opportunity.pk])
        self.client.post(close_url)
        self.assertEqual(self.client.post(close_url).status_code, 302)
        self.client.post(reopen_url)
        self.assertEqual(self.client.post(reopen_url).status_code, 302)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.status, CareOpportunity.Status.OPEN)
