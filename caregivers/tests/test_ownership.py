"""Only a caregiver can change their own profile and services, and service
prices are validated (active services need a price; no negative prices)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from ..forms import CaregiverServicesForm
from ..models import CaregiverService
from .test_caregivers import CaregiverTestData


class CaregiverOwnershipTests(CaregiverTestData):
    """A signed-in user can't edit another caregiver's profile or services."""

    def setUp(self):
        super().setUp()
        self.mine = self.make_caregiver(user=self.user)
        self.intruder = get_user_model().objects.create_user(
            "intruder", password="pw-12345!"
        )
        self.service = self.make_service(self.mine)
        self.client.force_login(self.intruder)

    def urls(self):
        pk, sid = self.mine.pk, self.service.pk
        return [
            reverse("edit_caregiver_profile", args=[pk]),
            reverse("services", args=[pk]),
            reverse("add_caregiver_service", args=[pk]),
            reverse("edit_caregiver_service", args=[pk, sid]),
            reverse("delete_caregiver_service", args=[pk, sid]),
        ]

    def test_other_users_cannot_open_management_pages(self):
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_other_users_cannot_edit_the_profile(self):
        response = self.client.post(
            reverse("edit_caregiver_profile", args=[self.mine.pk]),
            self.profile_data(name="HACKED"),
        )
        self.assertEqual(response.status_code, 404)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, "Chloe Shih")

    def test_other_users_cannot_delete_a_service(self):
        response = self.client.post(
            reverse("delete_caregiver_service", args=[self.mine.pk, self.service.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(CaregiverService.objects.filter(pk=self.service.pk).exists())

    def test_other_users_cannot_add_or_edit_services(self):
        self.client.post(
            reverse("add_caregiver_service", args=[self.mine.pk]),
            self.service_data(service_type=self.sitting.pk),
        )
        self.client.post(
            reverse("edit_caregiver_service", args=[self.mine.pk, self.service.pk]),
            self.service_data(price="1.00"),
        )
        self.assertEqual(
            CaregiverService.objects.filter(caregiver=self.mine).count(), 1
        )
        self.service.refresh_from_db()
        self.assertEqual(self.service.price, Decimal("25.00"))

    def test_signed_out_visitors_are_sent_to_log_in(self):
        self.client.logout()
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])

    def test_owner_can_still_manage_everything(self):
        self.client.force_login(self.user)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_profile_without_an_account_cannot_be_edited(self):
        legacy = self.make_caregiver(name="Old Profile")
        response = self.client.get(reverse("edit_caregiver_profile", args=[legacy.pk]))
        self.assertEqual(response.status_code, 404)


class EditButtonVisibilityTests(CaregiverTestData):
    def test_only_the_caregiver_sees_edit_profile(self):
        mine = self.make_caregiver(user=self.user)
        url = reverse("caregiver", args=[mine.pk])
        edit_url = reverse("edit_caregiver_profile", args=[mine.pk])

        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), edit_url)

        other = get_user_model().objects.create_user("owner2", password="pw-12345!")
        self.client.force_login(other)
        self.assertNotContains(self.client.get(url), edit_url)


class ServicePriceRulesTests(CaregiverTestData):
    def form(self, **overrides):
        return CaregiverServicesForm(data=self.service_data(**overrides))

    def test_active_service_can_skip_the_price(self):
        self.assertTrue(self.form(price="", is_active="on").is_valid())

    def test_inactive_service_can_be_saved_without_a_price(self):
        self.assertTrue(self.form(price="", is_active="").is_valid())

    def test_price_cannot_be_negative(self):
        form = self.form(price="-5.00")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["price"], ["Price can't be negative."])

    def test_free_service_is_allowed(self):
        self.assertTrue(self.form(price="0.00").is_valid())

    def test_price_input_has_a_minimum(self):
        self.assertIn('min="0"', str(self.form()["price"]))

    def test_add_page_saves_active_service_without_price(self):
        caregiver = self.make_caregiver(user=self.user)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("add_caregiver_service", args=[caregiver.pk]),
            self.service_data(price=""),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            CaregiverService.objects.filter(
                caregiver=caregiver, is_active=True
            ).exists()
        )
