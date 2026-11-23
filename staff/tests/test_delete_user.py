"""#93 Remove User Account: admins delete an account from the Users page.
It works like users deleting their own account (#48)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import ServiceType
from pets.models import Pet, PetType

from .test_user_list import LIST_URL, StaffTestData, detail_url

User = get_user_model()


def delete_url(user):
    return reverse("staff:delete_user", args=[user.pk])


class DeleteUserTests(StaffTestData):
    def test_delete_account_is_in_the_more_menu(self):
        # Kat's "More menu" design: Delete account sits under "…".
        response = self.client.get(detail_url(self.owner))
        self.assertContains(response, '<details class="staff-actions-more">')
        self.assertContains(response, "More actions")
        self.assertContains(response, "confirm=delete")
        self.assertContains(response, "Delete account")

    def test_deleted_accounts_have_no_page(self):
        response = self.client.get(detail_url(self.gone))
        self.assertEqual(response.status_code, 404)

    def test_delete_asks_for_confirmation_first(self):
        response = self.client.get(detail_url(self.owner) + "?confirm=delete")
        self.assertContains(response, "Delete Kat’s account?")
        self.assertContains(
            response,
            "This can’t be undone. Their profile, pets, bookings and posts "
            "will be removed.",
        )
        self.assertContains(response, f'action="{delete_url(self.owner)}"')
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_no_popup_for_an_account_that_cant_be_deleted(self):
        # Admins and deleted accounts aren't on the Users page.
        other_admin = User.objects.create_user("bo", is_staff=True)
        for account in (self.admin, other_admin, self.gone):
            response = self.client.get(detail_url(account) + "?confirm=delete")
            self.assertNotContains(response, "account?</h2>", status_code=404)

    def test_deleting_an_owner(self):
        dog = PetType.objects.get_or_create(name="Dog")[0]
        pet = Pet.objects.create(owner=self.owner, name="Miso", pet_type=dog)
        start = timezone.now() + timedelta(days=2)
        booking = Booking.objects.create(
            owner=self.owner,
            pet=pet,
            caregiver=self.sitter.caregiver_profile,
            service_type=ServiceType.objects.get_or_create(name="Dog walking")[0],
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=Booking.Status.ACCEPTED,
        )
        response = self.client.post(delete_url(self.owner), follow=True)
        # Kat's "Account deleted" design: the page moves on to the first
        # account, with a banner.
        self.assertRedirects(response, f"{LIST_URL}?deleted={self.owner.pk}")
        self.assertContains(response, "Kat W.’s account was deleted.")
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertEqual(self.owner.email, "")
        self.assertFalse(self.owner.has_usable_password())
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        # It leaves the list.
        self.assertNotIn(self.owner, response.context["page"])
        self.assertNotEqual(response.context["selected"], self.owner)

    def test_deleting_a_caregiver_stops_new_requests(self):
        self.client.post(delete_url(self.sitter))
        profile = self.sitter.caregiver_profile
        profile.refresh_from_db()
        self.assertFalse(profile.accepting_new_bookings)

    def test_a_deleted_user_is_logged_out(self):
        other = self.client_class()
        other.force_login(self.owner)
        self.client.post(delete_url(self.owner))
        response = other.get(reverse("pets:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_cant_delete_admins_yourself_or_deleted_accounts(self):
        other_admin = User.objects.create_user("bo", is_staff=True)
        for account in (other_admin, self.admin, self.gone):
            response = self.client.post(delete_url(account))
            self.assertIn(response.status_code, (403, 404))
        other_admin.refresh_from_db()
        self.assertTrue(other_admin.is_active)

    def test_only_admins_can_delete(self):
        self.client.force_login(self.sitter)
        response = self.client.post(delete_url(self.owner))
        self.assertEqual(response.status_code, 403)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_delete_needs_a_post(self):
        self.assertEqual(self.client.get(delete_url(self.owner)).status_code, 405)

    def test_deleted_banner_only_for_deleted_accounts(self):
        for value in (self.owner.pk, self.admin.pk, "999", "x"):
            response = self.client.get(LIST_URL, {"deleted": value})
            self.assertIsNone(response.context["deleted_account"])
            self.assertNotContains(response, "account was deleted.")
        response = self.client.get(LIST_URL, {"deleted": self.gone.pk})
        self.assertEqual(response.context["deleted_account"], self.gone)
