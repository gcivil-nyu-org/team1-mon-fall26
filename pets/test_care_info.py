"""
Tests for pet care information.

Owner side:     #20 feeding, #21 medication and special care, #23 emergency and vet.
Caregiver side: #84 view pet profile, #85 feeding, #86 medication, #88 emergency.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import CaregiverProfile, ServiceType

from .models import Pet, PetType

User = get_user_model()

CARE_INFO = {
    "food": "Timothy hay + fresh greens",
    "portion": "Unlimited hay, 1 cup greens",
    "feeding_times": "8:00 AM, 6:00 PM",
    "feeding_instructions": "Refill the water bottle each visit",
    "medications": "Probiotic (Bene-Bac)",
    "medication_dose": "1 g",
    "medication_schedule": "Once daily with morning greens",
    "special_care_instructions": "Scared of thunder",
    "vet_name": "Dr. Turkell, GoodVets",
    "vet_phone": "(718) 555-0142",
    "emergency_contact_name": "Joy Wang (cousin)",
    "emergency_contact_phone": "+1 917 555 0187",
}
# Only shown to the caregiver while a booking is happening.
CONTACT_FIELDS = ("vet_name", "vet_phone", "emergency_contact_name", "emergency_contact_phone")


class OwnerCareInfoTests(TestCase):
    """The owner adds, sees and edits care information (#20, #21, #23)."""

    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.client.login(username="alex", password="pass12345")
        self.dog = PetType.objects.get(name="Dog")

    def form_data(self, **overrides):
        data = {"name": "Milo", "pet_type": self.dog.pk, "age": 3, "age_unit": "years"}
        data.update(CARE_INFO)
        data.update(overrides)
        return data

    def test_care_information_is_saved_to_the_pet(self):
        self.client.post(reverse("pets:create"), self.form_data())
        pet = Pet.objects.get(name="Milo")
        for field, value in CARE_INFO.items():
            self.assertEqual(getattr(pet, field), value, field)

    def test_care_information_is_optional(self):
        blank = {field: "" for field in CARE_INFO}
        response = self.client.post(reverse("pets:create"), self.form_data(**blank))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Pet.objects.filter(name="Milo").exists())

    def test_form_shows_the_care_sections(self):
        response = self.client.get(reverse("pets:create"))
        for text in ("Food", "Portion", "Feeding times", "Feeding notes", "Medication",
                     "Dose", "Schedule", "Special care instructions", "Vet name &amp; clinic",
                     "Vet phone", "Emergency contact", "Emergency phone"):
            self.assertContains(response, text)

    def test_owner_page_shows_care_information(self):
        self.client.post(reverse("pets:create"), self.form_data())
        pet = Pet.objects.get(name="Milo")
        response = self.client.get(pet.get_absolute_url())
        for value in CARE_INFO.values():
            self.assertContains(response, value)
        self.assertContains(response, 'href="tel:(718)555-0142"')

    def test_owner_page_says_when_information_is_missing(self):
        pet = Pet.objects.create(owner=self.owner, name="Milo", pet_type=self.dog)
        response = self.client.get(pet.get_absolute_url())
        self.assertContains(response, "No feeding instructions yet.")
        self.assertContains(response, "No emergency or vet contacts yet.")
        self.assertNotContains(response, "Add them")
        self.assertNotContains(response, "Add special care notes")

    def test_owner_can_edit_care_information_later(self):
        pet = Pet.objects.create(owner=self.owner, name="Milo", pet_type=self.dog, **CARE_INFO)
        response = self.client.get(reverse("pets:edit", args=[pet.pk]))
        self.assertContains(response, CARE_INFO["feeding_instructions"])

        self.client.post(
            reverse("pets:edit", args=[pet.pk]),
            self.form_data(feeding_instructions="Half a cup, twice a day",
                           medications="", medication_dose="", medication_schedule=""),
        )
        pet.refresh_from_db()
        self.assertEqual(pet.feeding_instructions, "Half a cup, twice a day")
        self.assertEqual(pet.medications, "")

    def test_phone_numbers_must_look_like_phone_numbers(self):
        for bad in ("call me", "123", "1234567890123456"):
            response = self.client.post(
                reverse("pets:create"), self.form_data(vet_phone=bad)
            )
            self.assertContains(response, "Enter a phone number with 7 to 15 digits")
            self.assertContains(response, "Check the highlighted fields.")
        self.assertFalse(Pet.objects.exists())

    def test_contact_name_needs_a_phone_number(self):
        response = self.client.post(
            reverse("pets:create"),
            self.form_data(vet_phone="", emergency_contact_phone=""),
        )
        self.assertContains(response, "Add the vet&#x27;s phone number too.")
        self.assertContains(response, "Add a phone number for your emergency contact.")

    def test_emergency_phone_needs_a_name(self):
        response = self.client.post(
            reverse("pets:create"), self.form_data(emergency_contact_name="")
        )
        self.assertContains(response, "Add your emergency contact&#x27;s name.")

    def test_vet_phone_alone_is_fine(self):
        response = self.client.post(
            reverse("pets:create"), self.form_data(vet_name="")
        )
        self.assertEqual(response.status_code, 302)


class CaregiverPetViewTests(TestCase):
    """A caregiver views the pet's profile and care info (#84, #85, #86, #88)."""

    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.carer_user = User.objects.create_user("chloe", password="pass12345")
        self.other_carer_user = User.objects.create_user("dana", password="pass12345")
        self.caregiver = CaregiverProfile.objects.create(
            user=self.carer_user, name="Chloe Shih", service_area="Brooklyn"
        )
        self.other_caregiver = CaregiverProfile.objects.create(
            user=self.other_carer_user, name="Dana Ruiz", service_area="Queens"
        )
        dog = PetType.objects.get(name="Dog")
        self.pet = Pet.objects.create(
            owner=self.owner, name="Milo", pet_type=dog, **CARE_INFO
        )
        self.url = reverse("pets:care_view", args=[self.pet.pk])
        self.client.login(username="chloe", password="pass12345")

    def book(self, status=Booking.Status.ACCEPTED, caregiver=None, starts_in=timedelta(days=1)):
        start = timezone.now() + starts_in
        return Booking.objects.create(
            owner=self.owner,
            pet=self.pet,
            caregiver=caregiver or self.caregiver,
            service_type=ServiceType.objects.get(name="Dog walking"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=status,
        )

    def test_caregiver_with_accepted_booking_sees_full_profile(self):
        self.book()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Milo")
        for key, value in CARE_INFO.items():
            if key not in CONTACT_FIELDS:
                self.assertContains(response, value)
        self.assertContains(response, "Your upcoming care")

    def test_contacts_are_hidden_until_the_booking_starts(self):
        self.book()
        response = self.client.get(self.url)
        self.assertContains(response, "Contacts are only shown during the booking.")
        for key in CONTACT_FIELDS:
            self.assertNotContains(response, CARE_INFO[key])

    def test_profile_and_contacts_are_shown_during_the_visit(self):
        self.book(starts_in=timedelta(minutes=-30))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for key in CONTACT_FIELDS:
            self.assertContains(response, CARE_INFO[key])

    def test_no_access_without_an_accepted_booking(self):
        for status in (Booking.Status.PENDING, Booking.Status.DECLINED,
                       Booking.Status.CANCELLED, Booking.Status.COMPLETED):
            with self.subTest(status=status):
                Booking.objects.all().delete()
                self.book(status=status)
                self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_no_access_after_the_booking_ends(self):
        self.book(starts_in=timedelta(days=-2))
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_other_caregivers_cannot_see_it(self):
        self.book(caregiver=self.other_caregiver)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_owner_is_sent_to_their_own_pet_page(self):
        self.client.login(username="alex", password="pass12345")
        response = self.client.get(self.url)
        self.assertRedirects(response, self.pet.get_absolute_url())

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_caregiver_sees_message_when_owner_added_no_contacts(self):
        Pet.objects.filter(pk=self.pet.pk).update(
            vet_name="", vet_phone="",
            emergency_contact_name="", emergency_contact_phone="",
        )
        self.book(starts_in=timedelta(minutes=-30))
        response = self.client.get(self.url)
        self.assertContains(response, "Ask the owner before the visit.")
        self.assertNotContains(response, "Add them")

    def test_booking_pages_link_to_the_profile_once_accepted(self):
        booking = self.book(status=Booking.Status.PENDING)
        detail = reverse("bookings:booking_detail", args=[booking.pk])
        self.assertNotContains(self.client.get(detail), self.url)

        Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.ACCEPTED)
        self.assertContains(self.client.get(detail), self.url)
        requests_page = reverse("bookings:caregiver_requests") + "?status=accepted"
        self.assertContains(self.client.get(requests_page), self.url)


class PetPageDesignTests(TestCase):
    """Details from Kat's Figma for the pet pages."""

    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.client.login(username="alex", password="pass12345")
        self.pet = Pet.objects.create(
            owner=self.owner, name="Milo", pet_type=PetType.objects.get(name="Dog")
        )

    def test_profile_banner_links_to_find_a_caregiver(self):
        response = self.client.get(self.pet.get_absolute_url())
        self.assertContains(response, "Find a caregiver")
        self.assertContains(response, reverse("caregiver_list"))

    def test_photo_badge_links_to_edit(self):
        response = self.client.get(self.pet.get_absolute_url())
        self.assertContains(response, "aria-label=\"Add Milo's photo\"")

    def test_form_shows_pet_photo_upload(self):
        response = self.client.get(reverse("pets:create"))
        self.assertContains(response, "Pet photo")
        self.assertContains(response, "Upload photo")
        self.assertContains(response, "JPG or PNG, up to 5 MB")


class CareSummaryTests(TestCase):
    """Kat's Figma: care details split into fields, with a short summary for caregivers."""

    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.carer_user = User.objects.create_user("chloe", password="pass12345")
        self.caregiver = CaregiverProfile.objects.create(
            user=self.carer_user, name="Chloe Shih", service_area="Brooklyn"
        )
        self.pet = Pet.objects.create(
            owner=self.owner, name="Biscuit", pet_type=PetType.objects.get(name="Dog"), **CARE_INFO
        )

    def book(self, status, starts_in=timedelta(days=1)):
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

    def test_feeding_and_medication_summaries(self):
        self.assertEqual(
            self.pet.feeding_summary,
            "Timothy hay + fresh greens, Unlimited hay, 1 cup greens at 8:00 AM, 6:00 PM.",
        )
        self.assertEqual(
            self.pet.medication_summary, "Probiotic (Bene-Bac), 1 g, Once daily with morning greens."
        )
        self.assertEqual(Pet(name="Empty").feeding_summary, "")
        self.assertEqual(Pet(feeding_times="8 AM").feeding_summary, "8 AM.")

    def test_dose_needs_a_medication_name(self):
        self.client.login(username="alex", password="pass12345")
        response = self.client.post(
            reverse("pets:create"),
            {"name": "Milo", "pet_type": self.pet.pet_type.pk, "age": 2, "age_unit": "years",
             "medication_dose": "1 g"},
        )
        self.assertContains(response, "Add the medication&#x27;s name.")

    def test_request_panel_shows_care_summary_but_hides_contacts_until_accepted(self):
        self.client.login(username="chloe", password="pass12345")
        self.book(Booking.Status.PENDING)
        response = self.client.get(reverse("bookings:caregiver_requests"))
        self.assertContains(response, "Timothy hay + fresh greens")
        self.assertContains(response, "Probiotic (Bene-Bac)")
        self.assertContains(response, "Contacts are only shown during the booking.")
        self.assertNotContains(response, CARE_INFO["vet_phone"])

    def test_request_panel_hides_contacts_before_the_booking_starts(self):
        self.client.login(username="chloe", password="pass12345")
        self.book(Booking.Status.ACCEPTED)
        response = self.client.get(reverse("bookings:caregiver_requests") + "?status=accepted")
        self.assertContains(response, "Contacts are only shown during the booking.")
        self.assertNotContains(response, CARE_INFO["vet_phone"])

    def test_request_panel_shows_contacts_during_the_booking(self):
        self.client.login(username="chloe", password="pass12345")
        self.book(Booking.Status.ACCEPTED, starts_in=timedelta(minutes=-30))
        response = self.client.get(reverse("bookings:caregiver_requests") + "?status=accepted")
        self.assertContains(response, CARE_INFO["vet_phone"])
        self.assertContains(response, "Emergency: Joy Wang (cousin)")
