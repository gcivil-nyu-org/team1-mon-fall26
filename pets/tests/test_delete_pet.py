"""Story #24: update or delete a pet profile."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.forms import BookingRequestForm
from bookings.models import Booking
from caregivers.models import CaregiverProfile, ServiceType

from ..models import Pet, PetType

User = get_user_model()


class DeletePetTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.client.login(username="alex", password="pass12345")
        self.pet = Pet.objects.create(
            owner=self.owner, name="Milo", pet_type=PetType.objects.get(name="Dog")
        )
        self.url = reverse("pets:delete", args=[self.pet.pk])
        carer = User.objects.create_user("chloe", password="pass12345")
        self.caregiver = CaregiverProfile.objects.create(
            user=carer, name="Chloe Shih", service_area="Brooklyn"
        )

    def book(self, status, starts_in):
        start = timezone.now() + starts_in
        return Booking.objects.create(
            owner=self.owner,
            pet=self.pet,
            caregiver=self.caregiver,
            service_type=ServiceType.objects.get(name="Dog walking"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=status,
        )

    def assert_hidden_from_owner(self):
        # Gone from the pet cards (the booking panel may still mention past bookings).
        self.assertNotIn(
            self.pet, self.client.get(reverse("pets:list")).context["pets"]
        )
        for name in ("pets:detail", "pets:edit", "pets:delete"):
            self.assertEqual(
                self.client.get(reverse(name, args=[self.pet.pk])).status_code, 404
            )

    def test_edit_page_links_to_delete(self):
        response = self.client.get(reverse("pets:edit", args=[self.pet.pk]))
        self.assertContains(response, self.url)
        self.assertContains(response, "Delete pet profile")

    def test_asks_for_confirmation_first(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Delete Milo's profile?")
        self.assertContains(response, "Yes, delete Milo")
        self.assertTrue(Pet.objects.filter(pk=self.pet.pk).exists())

    def test_deleting_a_pet_without_bookings_removes_it(self):
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse("pets:list"))
        self.assertContains(response, "Milo&#x27;s profile was deleted.")
        self.assertFalse(Pet.objects.filter(pk=self.pet.pk).exists())
        self.assertNotIn(
            self.pet, self.client.get(reverse("pets:list")).context["pets"]
        )

    def test_pet_with_past_bookings_is_hidden_but_history_stays(self):
        booking = self.book(Booking.Status.COMPLETED, timedelta(days=-3))
        self.client.post(self.url)

        self.pet.refresh_from_db()
        self.assertIsNotNone(self.pet.deleted_at)
        self.assert_hidden_from_owner()
        # The old booking still shows which pet it was for.
        self.assertContains(self.client.get(booking.get_absolute_url()), "Milo")

    def test_deleted_pet_cannot_be_booked(self):
        self.book(Booking.Status.DECLINED, timedelta(days=-3))
        self.client.post(self.url)
        form = BookingRequestForm(owner=self.owner)
        self.assertNotIn(self.pet, form.fields["pet"].queryset)

    def test_cannot_delete_with_a_pending_request(self):
        self.book(Booking.Status.PENDING, timedelta(days=2))
        response = self.client.get(self.url)
        self.assertContains(response, "Milo has upcoming bookings")
        self.assertNotContains(response, "Yes, delete Milo")

        response = self.client.post(self.url, follow=True)
        self.assertContains(response, "Cancel them first")
        self.pet.refresh_from_db()
        self.assertIsNone(self.pet.deleted_at)

    def test_cannot_delete_during_accepted_care(self):
        self.book(Booking.Status.ACCEPTED, timedelta(minutes=-30))
        self.client.post(self.url)
        self.pet.refresh_from_db()
        self.assertIsNone(self.pet.deleted_at)

    def test_finished_or_stale_bookings_do_not_block(self):
        self.book(Booking.Status.ACCEPTED, timedelta(days=-2))  # care already over
        self.book(
            Booking.Status.PENDING, timedelta(days=-2)
        )  # never answered, start passed
        self.client.post(self.url)
        self.pet.refresh_from_db()
        self.assertIsNotNone(self.pet.deleted_at)

    def test_only_the_owner_can_delete(self):
        User.objects.create_user("sam", password="pass12345")
        self.client.login(username="sam", password="pass12345")
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertTrue(Pet.objects.filter(pk=self.pet.pk).exists())

    def test_login_required(self):
        self.client.logout()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Pet.objects.filter(pk=self.pet.pk).exists())
