"""#91 View User Account Details: profile basics, type and status, pets and
recent bookings, so an admin has context before acting on an account."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from bookings.models import Booking
from caregivers.models import CaregiverService, ServiceType
from pets.models import Pet, PetType
from staff.accounts import RECENT_BOOKINGS

from .test_user_list import StaffTestData, detail_url


class DetailTests(StaffTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.owner.account_profile.neighborhood = "Park Slope"
        cls.owner.account_profile.save()
        dog = PetType.objects.get_or_create(name="Dog")[0]
        cls.biscuit = Pet.objects.create(
            owner=cls.owner, name="Biscuit", pet_type=dog, breed="Beagle"
        )
        cls.old_pet = Pet.objects.create(
            owner=cls.owner, name="Pepper", pet_type=dog, deleted_at=timezone.now()
        )
        cls.walking = ServiceType.objects.get_or_create(name="Dog walking")[0]
        cls.drop_in = ServiceType.objects.get_or_create(name="Drop-in visit")[0]
        caregiver = cls.sitter.caregiver_profile
        CaregiverService.objects.create(
            caregiver=caregiver,
            service_type=cls.walking,
            price=Decimal("25.00"),
            price_unit="walk",
        )
        CaregiverService.objects.create(
            caregiver=caregiver, service_type=cls.drop_in, is_active=False
        )

    def book(self, days, status=Booking.Status.PENDING):
        start = timezone.now() + timedelta(days=days)
        return Booking.objects.create(
            owner=self.owner,
            pet=self.biscuit,
            caregiver=self.sitter.caregiver_profile,
            service_type=self.walking,
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=status,
        )

    def test_pet_owner_sees_profile_pets_and_bookings(self):
        self.book(2, Booking.Status.ACCEPTED)
        response = self.client.get(detail_url(self.owner))
        for text in (
            "Neighborhood",
            "Park Slope",
            "Biscuit",
            "Dog · Beagle",
            "Pepper",
            "Deleted ",
            "Biscuit · Dog walking",
            "Caregiver: Chloe Shih",
            "Accepted",
        ):
            self.assertContains(response, text)
        self.assertNotContains(response, "Caregiver profile")

    def test_caregiver_sees_profile_services_and_bookings(self):
        self.book(-3, Booking.Status.COMPLETED)
        response = self.client.get(detail_url(self.sitter))
        self.assertContains(response, "Caregiver profile")
        self.assertContains(response, "View public profile")
        self.assertContains(response, "Accepting")
        self.assertContains(response, "Dog walking · $25.00 per walk")
        self.assertNotContains(response, "Drop-in visit")  # inactive service
        self.assertContains(response, "Owner: Kat W")
        self.assertContains(response, "Completed")
        self.assertNotContains(response, "<h2>Pets</h2>", html=True)

    def test_empty_sections_say_so(self):
        response = self.client.get(detail_url(self.new))
        self.assertContains(response, "No pet profiles.")
        self.assertContains(response, "No bookings yet.")

    def test_caregiver_without_services(self):
        CaregiverService.objects.filter(caregiver__user=self.sitter).delete()
        response = self.client.get(detail_url(self.sitter))
        self.assertContains(response, "No services listed.")

    def test_only_the_most_recent_bookings(self):
        bookings = [self.book(day) for day in range(1, RECENT_BOOKINGS + 3)]
        response = self.client.get(detail_url(self.owner))
        shown = list(response.context["bookings"])
        self.assertEqual(len(shown), RECENT_BOOKINGS)
        self.assertEqual(shown[0], bookings[-1])
        self.assertContains(
            response,
            f"The {RECENT_BOOKINGS} most recent of {RECENT_BOOKINGS + 2}.",
        )

    def test_other_peoples_bookings_are_not_shown(self):
        self.book(1)
        response = self.client.get(detail_url(self.new))
        self.assertEqual(list(response.context["bookings"]), [])
