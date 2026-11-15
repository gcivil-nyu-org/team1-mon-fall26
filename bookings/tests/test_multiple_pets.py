"""One booking request for several of the owner's pets. The caregiver works out
the price with the owner, so nothing about prices changes."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from pets.models import Pet, PetType
from reviews.models import Review
from reviews.templatetags.review_tags import pet_rating_line, pet_reviews

from ..forms import BookingRequestForm
from ..models import Booking
from .test_bookings import BookingTestData

CREATE_URL = reverse("bookings:booking_create")


class MultiplePetsData(BookingTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cat = PetType.objects.get_or_create(name="Cat")[0]
        cls.luna = Pet.objects.create(owner=cls.owner, name="Luna", pet_type=cat)
        cls.archie = Pet.objects.create(
            owner=cls.owner, name="Archie", pet_type=cls.pet.pet_type
        )
        cls.sitter = get_user_model().objects.create_user(
            "sitter", password="pw-12345!"
        )
        cls.caregiver.user = cls.sitter
        cls.caregiver.save()

    def book(self, *pets, status=Booking.Status.PENDING, starts_in=timedelta(days=1)):
        booking = self.make_booking(
            pet=pets[0], status=status, start_time=timezone.now() + starts_in
        )
        booking.end_time = booking.start_time + timedelta(hours=2)
        booking.save()
        booking.pets.set(pets)
        return booking


class ModelTests(MultiplePetsData):
    def test_names_and_order(self):
        booking = self.book(self.pet, self.luna, self.archie)
        booking = Booking.objects.get(pk=booking.pk)
        self.assertEqual(
            [p.name for p in booking.all_pets], ["Biscuit", "Archie", "Luna"]
        )
        self.assertEqual(booking.pet_names, "Biscuit, Archie & Luna")
        booking.pets.set([self.pet, self.luna])
        self.assertEqual(Booking.objects.get(pk=booking.pk).pet_names, "Biscuit & Luna")

    def test_one_pet_without_the_list_filled_in(self):
        booking = self.make_booking()
        self.assertEqual(booking.pet_names, "Biscuit")
        self.assertEqual(list(Booking.for_pet(self.pet)), [booking])

    def test_for_pet_finds_every_pet(self):
        booking = self.book(self.pet, self.luna)
        self.assertEqual(list(Booking.for_pet(self.luna)), [booking])
        self.assertEqual(list(Booking.for_pet(self.pet)), [booking])
        self.assertEqual(list(Booking.for_pet(self.archie)), [])


class RequestTests(MultiplePetsData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_form_offers_checkboxes_and_a_price_note(self):
        response = self.client.get(CREATE_URL)
        self.assertContains(response, "Which pets?")
        self.assertContains(response, 'type="checkbox" name="pets"', count=3)
        self.assertContains(response, "the caregiver confirms the price")

    def test_several_pets_can_be_preselected(self):
        response = self.client.get(
            CREATE_URL, {"pet": [self.pet.pk, self.luna.pk, "x"]}
        )
        self.assertEqual(
            response.context["form"].initial["pets"],
            [str(self.pet.pk), str(self.luna.pk)],
        )

    def test_request_for_two_pets(self):
        data = self.form_data(pets=[self.luna.pk, self.pet.pk])
        response = self.client.post(CREATE_URL, data)
        booking = Booking.objects.get()
        self.assertRedirects(response, booking.get_absolute_url())
        # The first in name order is the booking's first pet.
        self.assertEqual(booking.pet, self.pet)
        self.assertEqual(set(booking.pets.all()), {self.pet, self.luna})
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "<h1>Biscuit &amp; Luna · Dog walking</h1>")
        self.assertContains(response, "Biscuit &amp; Luna · Dog walking")
        # A declined request offers to ask someone else for the same pets.
        booking.status = Booking.Status.DECLINED
        booking.save()
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, f"?pet={self.pet.pk}&amp;pet={self.luna.pk}")

    def test_form_save_without_the_view(self):
        form = BookingRequestForm(
            data=self.form_data(pets=[self.archie.pk, self.luna.pk]), owner=self.owner
        )
        self.assertTrue(form.is_valid())
        booking = form.save(commit=False)
        booking.owner = self.owner
        booking.save()
        form.save_m2m()
        self.assertEqual(booking.pet, self.archie)
        booking = form.save()
        self.assertEqual(booking.pets.count(), 2)

    def test_lists_show_every_pet(self):
        self.book(self.pet, self.luna)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, "Biscuit &amp; Luna · Dog walking")


class CaregiverTests(MultiplePetsData):
    def setUp(self):
        self.client.force_login(self.sitter)

    def test_request_panel_shows_each_pet(self):
        self.luna.special_care_instructions = "Shy with strangers."
        self.luna.save()
        booking = self.book(self.pet, self.luna)
        response = self.client.get(
            reverse("bookings:caregiver_requests"), {"b": booking.pk}
        )
        self.assertContains(response, "<strong>Biscuit &amp; Luna</strong>")
        self.assertContains(response, "2 pets")
        self.assertContains(response, "you and the owner agree on the price")
        self.assertContains(response, 'class="request-pet-name">Luna')

    def test_detail_and_care_pages_for_every_pet(self):
        self.luna.special_care_instructions = "Shy with strangers."
        self.luna.save()
        booking = self.book(self.pet, self.luna, status=Booking.Status.ACCEPTED)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "About Luna")
        self.assertContains(response, "Luna's care needs")
        self.assertContains(response, "Shy with strangers.")
        self.assertContains(response, "agree on the price")
        care = self.client.get(reverse("pets:care_view", args=[self.luna.pk]))
        self.assertEqual(care.status_code, 200)
        self.assertEqual(list(care.context["care_bookings"]), [booking])
        self.assertEqual(
            self.client.get(
                reverse("pets:care_view", args=[self.archie.pk])
            ).status_code,
            404,
        )

    def test_accept_message_names_every_pet(self):
        booking = self.book(self.pet, self.luna)
        response = self.client.post(
            reverse("bookings:booking_respond", args=[booking.pk]),
            {"action": "accept"},
            follow=True,
        )
        self.assertContains(response, "Request accepted: Biscuit &amp; Luna")

    def test_review_asks_about_every_pet(self):
        booking = self.book(
            self.pet,
            self.luna,
            status=Booking.Status.COMPLETED,
            starts_in=timedelta(days=-2),
        )
        response = self.client.get(reverse("reviews:create", args=[booking.pk]))
        self.assertContains(response, "How were Biscuit &amp; Luna and")
        self.assertContains(response, "How were Biscuit &amp; Luna? Was")
        Review.objects.create(
            booking=booking, author=self.sitter, role=Review.Role.CAREGIVER, rating=5
        )
        # The review counts for each pet, not only the first one picked.
        for pet in (self.pet, self.luna):
            self.assertEqual(pet_rating_line(pet)["summary"]["count"], 1)
            self.assertEqual(pet_reviews({}, pet)["summary"]["count"], 1)


class DeletePetTests(MultiplePetsData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_a_pet_in_an_upcoming_group_booking_cannot_be_deleted(self):
        self.book(self.pet, self.luna)
        response = self.client.post(reverse("pets:delete", args=[self.luna.pk]))
        self.assertRedirects(
            response,
            reverse("pets:delete", args=[self.luna.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(Pet.objects.filter(pk=self.luna.pk).exists())

    def test_a_pet_with_past_group_bookings_is_hidden_not_removed(self):
        booking = self.book(
            self.pet,
            self.luna,
            status=Booking.Status.COMPLETED,
            starts_in=timedelta(days=-3),
        )
        self.client.post(reverse("pets:delete", args=[self.luna.pk]))
        self.luna.refresh_from_db()
        self.assertIsNotNone(self.luna.deleted_at)
        self.assertIn(self.luna, booking.pets.all())
