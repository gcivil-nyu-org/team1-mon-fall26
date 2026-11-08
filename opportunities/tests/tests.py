from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.models import CaregiverProfile, ServiceType
from pets.models import Pet, PetType

from opportunities.forms import CareOpportunityForm
from opportunities.models import CareOpportunity, CareOpportunityInterest


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

    def test_owner_sees_active_interested_caregiver(self):
        interest = CareOpportunityInterest.objects.create(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
            is_active=True,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["interested_caregivers"]), [interest])
        self.assertContains(response, self.caregiver_profile.name)
        self.assertContains(response, "View profile")

    def test_owner_sees_correct_number_of_interested_caregivers(self):
        User = get_user_model()
        second_user = User.objects.create_user(
            username="second_interested_caregiver", password="test-pass-123"
        )
        second_caregiver = CaregiverProfile.objects.create(
            user=second_user, name="Second Caregiver", service_area="Queens"
        )
        for caregiver in (self.caregiver_profile, second_caregiver):
            CareOpportunityInterest.objects.create(
                caregiver=caregiver, opportunity=self.opportunity, is_active=True
            )

        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:list"))

        self.assertEqual(len(response.context["interested_caregivers"]), 2)
        self.assertContains(response, self.caregiver_profile.name)
        self.assertContains(response, second_caregiver.name)

    def test_owner_does_not_see_withdrawn_interest(self):
        CareOpportunityInterest.objects.create(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
            is_active=False,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:list"))

        self.assertEqual(list(response.context["interested_caregivers"]), [])
        self.assertNotContains(response, self.caregiver_profile.name)
        self.assertContains(
            response, "No one yet. Interested caregivers will show up here."
        )

    def test_owner_only_sees_interest_for_selected_own_post(self):
        second_post = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=self.service,
            start_time=self.start + timedelta(days=1),
            end_time=self.end + timedelta(days=1),
            location="Queens",
        )
        CareOpportunityInterest.objects.create(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
            is_active=True,
        )
        self.client.force_login(self.owner)
        url = reverse("opportunities:list")

        response = self.client.get(url, {"post": second_post.pk})
        self.assertEqual(response.context["selected"], second_post)
        self.assertEqual(list(response.context["interested_caregivers"]), [])
        self.assertNotContains(response, self.caregiver_profile.name)

        response = self.client.get(url, {"post": self.opportunity.pk})
        self.assertEqual(len(response.context["interested_caregivers"]), 1)
        self.assertContains(response, self.caregiver_profile.name)

        other_post = CareOpportunity.objects.create(
            owner=self.other_user,
            pet=self.other_pet,
            service_type=self.service,
            start_time=self.start,
            end_time=self.end,
            location="Other owner's location",
        )
        response = self.client.get(url, {"post": other_post.pk})
        self.assertNotEqual(response.context["selected"], other_post)
        self.assertNotIn(
            other_post,
            response.context["open_posts"],
        )


class CareOpportunityBrowseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="browse_owner", password="test-pass-123"
        )
        cls.caregiver_user = User.objects.create_user(
            username="browse_caregiver", password="test-pass-123"
        )
        cls.pet_type = PetType.objects.get_or_create(name="Rabbit")[0]
        cls.service = ServiceType.objects.get_or_create(name="Feeding")[0]
        cls.pet = Pet.objects.create(
            owner=cls.owner, name="Pepper", pet_type=cls.pet_type
        )
        cls.caregiver_profile = CaregiverProfile.objects.create(
            user=cls.caregiver_user,
            name="Caregiver Test",
            service_area="Brooklyn",
        )
        start = timezone.now() + timedelta(days=5)
        cls.opportunity = CareOpportunity.objects.create(
            owner=cls.owner,
            pet=cls.pet,
            service_type=cls.service,
            start_time=start,
            end_time=start + timedelta(hours=2),
            location="Park Slope",
        )

    def test_caregiver_can_browse_open_opportunities(self):
        self.client.force_login(self.caregiver_user)
        response = self.client.get(reverse("opportunities:browse"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.opportunity, response.context["posts"])
        self.assertEqual(response.context["selected"], self.opportunity)

    def test_filter_opportunities_by_service(self):
        other_service, _ = ServiceType.objects.get_or_create(name="Walking")
        other_post = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=other_service,
            start_time=self.opportunity.start_time,
            end_time=self.opportunity.end_time,
            location="Queens",
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            reverse("opportunities:browse"), {"service": self.service.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["posts"], [self.opportunity])
        self.assertNotIn(other_post, response.context["posts"])

    def test_filter_opportunities_by_pet_type(self):
        other_type, _ = PetType.objects.get_or_create(name="Dog")
        other_pet = Pet.objects.create(
            owner=self.owner, name="Buddy", pet_type=other_type
        )
        other_post = CareOpportunity.objects.create(
            owner=self.owner,
            pet=other_pet,
            service_type=self.service,
            start_time=self.opportunity.start_time,
            end_time=self.opportunity.end_time,
            location="Queens",
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            reverse("opportunities:browse"), {"pet_type": self.pet_type.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["posts"], [self.opportunity])
        self.assertNotIn(other_post, response.context["posts"])

    def test_combined_filters_and_selected_post(self):
        second = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=self.service,
            start_time=self.opportunity.start_time + timedelta(days=1),
            end_time=self.opportunity.end_time + timedelta(days=1),
            location="Queens",
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            reverse("opportunities:browse"),
            {
                "service": str(self.service.pk),
                "pet_type": str(self.pet_type.pk),
                "post": str(second.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["posts"]), 2)
        self.assertEqual(response.context["selected"], second)
        self.assertEqual(response.context["selected_service"], str(self.service.pk))
        self.assertEqual(response.context["selected_pet_type"], str(self.pet_type.pk))

    def test_invalid_filters_are_ignored_and_unknown_selection_falls_back(self):
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            reverse("opportunities:browse"),
            {
                "service": "not-a-number",
                "pet_type": "nope",
                "post": "999999",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["posts"], [self.opportunity])
        self.assertEqual(response.context["selected"], self.opportunity)

    def test_browse_hides_closed_and_deleted_pet_posts(self):
        closed = CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=self.service,
            start_time=self.opportunity.start_time,
            end_time=self.opportunity.end_time,
            location="Closed",
            status=CareOpportunity.Status.CLOSED,
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.get(reverse("opportunities:browse"))
        self.assertNotIn(closed, response.context["posts"])
        self.pet.deleted_at = timezone.now()
        self.pet.save(update_fields=["deleted_at"])
        response = self.client.get(reverse("opportunities:browse"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["posts"], [])
        self.assertIsNone(response.context["selected"])

    def test_browse_excludes_own_posts(self):
        own_pet = Pet.objects.create(
            owner=self.caregiver_user,
            name="My Pet",
            pet_type=self.pet_type,
        )
        own_post = CareOpportunity.objects.create(
            owner=self.caregiver_user,
            pet=own_pet,
            service_type=self.service,
            start_time=self.opportunity.start_time,
            end_time=self.opportunity.end_time,
            location="Home",
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.get(reverse("opportunities:browse"))
        self.assertNotIn(own_post, response.context["posts"])
        self.assertIn(self.opportunity, response.context["posts"])

    def test_browse_requires_login_and_caregiver_profile(self):
        url = reverse("opportunities:browse")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)
        self.client.force_login(self.owner)
        response = self.client.get(url)
        self.assertRedirects(response, reverse("opportunities:list"))

    def test_interest_requires_post_and_login(self):
        url = reverse("opportunities:interest", args=[self.opportunity.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)
        self.client.force_login(self.caregiver_user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_caregiver_can_express_interest(self):
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:interest", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("interest=added", response.url)
        interest = CareOpportunityInterest.objects.get(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
        )
        self.assertTrue(interest.is_active)
        browse = self.client.get(reverse("opportunities:browse"))
        self.assertTrue(browse.context["posts"][0].caregiver_interested)

    def test_repeated_interest_does_not_duplicate_record(self):
        self.client.force_login(self.caregiver_user)
        url = reverse("opportunities:interest", args=[self.opportunity.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(CareOpportunityInterest.objects.count(), 1)
        self.assertTrue(CareOpportunityInterest.objects.get().is_active)

    def test_withdraw_interest_preserves_record(self):
        interest = CareOpportunityInterest.objects.create(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
            is_active=True,
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:withdraw_interest", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("interest=withdrawn", response.url)
        interest.refresh_from_db()
        self.assertFalse(interest.is_active)
        self.assertEqual(CareOpportunityInterest.objects.count(), 1)
        browse = self.client.get(reverse("opportunities:browse"))
        self.assertFalse(browse.context["posts"][0].caregiver_interested)

    def test_reactivate_interest_reuses_record(self):
        interest = CareOpportunityInterest.objects.create(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
            is_active=False,
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:interest", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 302)
        interest.refresh_from_db()
        self.assertTrue(interest.is_active)
        self.assertEqual(CareOpportunityInterest.objects.count(), 1)

    def test_withdraw_without_existing_interest_is_safe(self):
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:withdraw_interest", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_interest_actions_require_caregiver_profile(self):
        self.client.force_login(self.owner)
        for name in ("interest", "withdraw_interest"):
            with self.subTest(name=name):
                response = self.client.post(
                    reverse(f"opportunities:{name}", args=[self.opportunity.pk])
                )
                self.assertRedirects(
                    response,
                    reverse("opportunities:browse"),
                    fetch_redirect_response=False,
                )
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_cannot_express_interest_in_closed_post(self):
        self.opportunity.status = CareOpportunity.Status.CLOSED
        self.opportunity.save(update_fields=["status"])
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:interest", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_cannot_express_interest_in_deleted_pet_post(self):
        self.pet.deleted_at = timezone.now()
        self.pet.save(update_fields=["deleted_at"])
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:interest", args=[self.opportunity.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_cannot_express_interest_in_own_post(self):
        own_pet = Pet.objects.create(
            owner=self.caregiver_user,
            name="Own Pet",
            pet_type=self.pet_type,
        )
        own_post = CareOpportunity.objects.create(
            owner=self.caregiver_user,
            pet=own_pet,
            service_type=self.service,
            start_time=self.opportunity.start_time,
            end_time=self.opportunity.end_time,
            location="Home",
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.post(
            reverse("opportunities:interest", args=[own_post.pk])
        )
        self.assertRedirects(response, reverse("opportunities:browse"))
        self.assertFalse(CareOpportunityInterest.objects.exists())

    def test_withdraw_is_post_only_and_login_required(self):
        url = reverse("opportunities:withdraw_interest", args=[self.opportunity.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.caregiver_user)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_interest_string_representation(self):
        interest = CareOpportunityInterest.objects.create(
            caregiver=self.caregiver_profile,
            opportunity=self.opportunity,
            is_active=True,
        )

        expected = (
            f"{self.caregiver_profile.pk} interested in " f"{self.opportunity.pk}: True"
        )

        self.assertEqual(str(interest), expected)


class CareOpportunityFigmaDetailsTests(CareOpportunityTests):
    """Owner names, in-panel statuses and messaging shown in the Figma frames."""

    def test_close_and_reopen_show_status_in_the_panel(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("opportunities:close", args=[self.opportunity.pk]), follow=True
        )
        self.assertContains(response, "Caregivers can’t see this post anymore.")
        response = self.client.post(
            reverse("opportunities:reopen", args=[self.opportunity.pk]), follow=True
        )
        self.assertContains(response, "Caregivers can see this post again.")

    def test_closed_banner_only_right_after_closing(self):
        self.opportunity.status = CareOpportunity.Status.CLOSED
        self.opportunity.save()
        self.client.force_login(self.owner)
        response = self.client.get(
            f"{reverse('opportunities:list')}?post={self.opportunity.pk}"
        )
        self.assertNotContains(response, "Caregivers can’t see this post anymore.")
        self.assertContains(response, "No caregivers were interested.")

    def test_list_shows_interest_count(self):
        CareOpportunityInterest.objects.create(
            opportunity=self.opportunity, caregiver=self.caregiver_profile
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:list"))
        self.assertContains(response, "1 interested")
        self.assertContains(
            response,
            reverse("messaging:message_caregiver", args=[self.caregiver_profile.pk]),
        )

    def test_new_post_starts_with_owner_neighborhood(self):
        from accounts.models import AccountProfile

        AccountProfile.objects.update_or_create(
            user=self.owner, defaults={"neighborhood": "Park Slope"}
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:create"))
        self.assertTrue(
            response.context["form"]["location"].value().startswith("Park Slope")
        )

    def test_blank_post_shows_specific_errors(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("opportunities:create"), {})
        self.assertContains(response, "Required fields can’t be left blank.")
        for message in ("Pick a pet.", "Pick a service.", "Choose a start date."):
            self.assertContains(response, message)

    def test_caregiver_can_message_post_owner(self):
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            reverse("opportunities:message_owner", args=[self.opportunity.pk])
        )
        from messaging.models import Conversation

        conversation = Conversation.objects.get(
            owner=self.owner, caregiver=self.caregiver_profile, booking=None
        )
        self.assertRedirects(response, conversation.get_absolute_url())

    def test_owner_without_caregiver_profile_cannot_message_owner(self):
        self.client.force_login(self.other_user)
        response = self.client.get(
            reverse("opportunities:message_owner", args=[self.opportunity.pk])
        )
        self.assertRedirects(
            response, reverse("opportunities:browse"), fetch_redirect_response=False
        )

    def test_browse_names_the_owner(self):
        self.owner.first_name, self.owner.last_name = "Kat", "Wu"
        self.owner.save()
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            f"{reverse('opportunities:browse')}?post={self.opportunity.pk}"
        )
        self.assertContains(response, "Owner: Kat W.")
        self.assertContains(response, "Message Kat")
        self.assertContains(response, "Note from Kat")

    def test_unknown_neighborhood_is_used_as_typed(self):
        from accounts.models import AccountProfile

        AccountProfile.objects.update_or_create(
            user=self.owner, defaults={"neighborhood": "Somewhere Else"}
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("opportunities:create"))
        self.assertEqual(response.context["form"]["location"].value(), "Somewhere Else")

    def test_browse_shows_distance_from_the_caregiver(self):
        CaregiverProfile.objects.filter(pk=self.caregiver_profile.pk).update(
            latitude=40.6710, longitude=-73.9814
        )
        self.opportunity.location = "Park Slope, Brooklyn"
        self.opportunity.save()
        self.client.force_login(self.caregiver_user)
        response = self.client.get(reverse("opportunities:browse"))
        self.assertContains(response, "Park Slope ·")
        self.assertContains(response, " mi</small>")

    def test_caregiver_messaging_their_own_post_goes_back_to_it(self):
        own_pet = Pet.objects.create(
            owner=self.caregiver_user, name="Own", pet_type=self.pet_type
        )
        own_post = CareOpportunity.objects.create(
            owner=self.caregiver_user,
            pet=own_pet,
            service_type=self.service,
            start_time=self.start,
            end_time=self.end,
            location="Park Slope",
        )
        self.client.force_login(self.caregiver_user)
        response = self.client.get(
            reverse("opportunities:message_owner", args=[own_post.pk])
        )
        self.assertRedirects(
            response,
            f"{reverse('opportunities:browse')}?post={own_post.pk}",
            fetch_redirect_response=False,
        )
