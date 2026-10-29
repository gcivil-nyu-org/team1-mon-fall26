"""Stories #62 (rate a completed service), #63 (write a review) and #66 (rate an owner and pet)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import CaregiverProfile, ServiceType
from pets.models import Pet, PetType

from ..models import Review

User = get_user_model()


class ReviewTestData(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "kat", password="pass12345", first_name="Kat"
        )
        self.carer = User.objects.create_user(
            "chloe", password="pass12345", first_name="Chloe"
        )
        self.caregiver = CaregiverProfile.objects.create(
            user=self.carer, name="Chloe Shih", service_area="Brooklyn"
        )
        self.pet = Pet.objects.create(
            owner=self.owner, name="Biscuit", pet_type=PetType.objects.get(name="Dog")
        )
        self.booking = self.book(Booking.Status.COMPLETED)
        self.url = reverse("reviews:create", args=[self.booking.pk])

    def book(self, status, pet=None):
        start = timezone.now() - timedelta(days=2)
        return Booking.objects.create(
            owner=self.owner,
            pet=pet or self.pet,
            caregiver=self.caregiver,
            service_type=ServiceType.objects.get(name="Dog walking"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=status,
        )

    def login(self, user):
        self.client.force_login(user)


class OwnerReviewTests(ReviewTestData):
    """#62 and #63: the owner rates and reviews the caregiver."""

    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def test_completed_booking_offers_a_review(self):
        response = self.client.get(self.booking.get_absolute_url())
        self.assertContains(response, "How did Chloe Shih do?")
        self.assertContains(response, self.url)

    def test_rating_and_feedback_are_saved_to_the_booking(self):
        response = self.client.post(
            self.url, {"rating": 5, "comment": "Biscuit came home happy!"}
        )
        self.assertRedirects(response, self.booking.get_absolute_url())
        review = Review.objects.get()
        self.assertEqual(review.booking, self.booking)
        self.assertEqual(review.author, self.owner)
        self.assertEqual(review.role, Review.Role.OWNER)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Biscuit came home happy!")

    def test_rating_alone_is_enough(self):
        self.client.post(self.url, {"rating": 4})
        self.assertEqual(Review.objects.get().comment, "")

    def test_rating_must_be_1_to_5(self):
        for bad in ("", "0", "6", "great"):
            response = self.client.post(self.url, {"rating": bad})
            self.assertEqual(response.status_code, 200)
        self.assertContains(
            self.client.post(self.url, {}), "Choose a rating from 1 to 5 stars."
        )
        self.assertFalse(Review.objects.exists())

    def test_review_appears_on_the_caregivers_profile(self):
        self.client.post(self.url, {"rating": 4, "comment": "On time and kind"})
        other = Pet.objects.create(
            owner=self.owner, name="Miso", pet_type=PetType.objects.get(name="Cat")
        )
        second = self.book(Booking.Status.COMPLETED, pet=other)
        self.client.post(reverse("reviews:create", args=[second.pk]), {"rating": 5})

        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertContains(response, "Reviews from pet owners")
        self.assertContains(response, "On time and kind")
        self.assertContains(response, "4.5")
        self.assertContains(response, "2 reviews")

    def test_booking_shows_your_review_afterwards(self):
        self.client.post(self.url, {"rating": 3, "comment": "Fine"})
        response = self.client.get(self.booking.get_absolute_url())
        self.assertContains(response, "Your review")
        self.assertContains(response, 'aria-label="3 out of 5 stars"')
        self.assertNotContains(response, "Leave a review")

    def test_only_one_review_per_booking(self):
        self.client.post(self.url, {"rating": 5})
        response = self.client.post(self.url, {"rating": 1}, follow=True)
        self.assertContains(response, "already reviewed this booking")
        self.assertEqual(Review.objects.get().rating, 5)

    def test_database_also_blocks_a_second_review(self):
        Review.objects.create(
            booking=self.booking, author=self.owner, role="owner", rating=5
        )
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                booking=self.booking, author=self.owner, role="owner", rating=4
            )

    def test_only_after_the_booking_is_completed(self):
        for status in (
            Booking.Status.PENDING,
            Booking.Status.ACCEPTED,
            Booking.Status.DECLINED,
            Booking.Status.CANCELLED,
        ):
            with self.subTest(status=status):
                booking = self.book(status)
                url = reverse("reviews:create", args=[booking.pk])
                response = self.client.post(url, {"rating": 5}, follow=True)
                self.assertContains(response, "once the booking is completed")
                self.assertNotContains(self.client.get(booking.get_absolute_url()), url)
        self.assertFalse(Review.objects.exists())


class CaregiverReviewTests(ReviewTestData):
    """#66 (and the caregiver side of #62/#63): the caregiver reviews the owner and pet."""

    def setUp(self):
        super().setUp()
        self.login(self.carer)

    def test_caregiver_review_is_about_the_owner_and_pet(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Review Kat &amp; Biscuit")
        self.client.post(
            self.url, {"rating": 4, "comment": "Sweet dog, pulls on the leash"}
        )
        review = Review.objects.get()
        self.assertEqual(review.role, Review.Role.CAREGIVER)
        self.assertEqual(review.booking, self.booking)

    def test_offered_in_the_request_panel_and_booking_page(self):
        panel = self.client.get(reverse("bookings:caregiver_requests") + "?status=all")
        self.assertContains(panel, "How was caring for Biscuit?")
        self.assertContains(self.client.get(self.booking.get_absolute_url()), self.url)

    def test_review_appears_on_the_pet_profile(self):
        self.client.post(
            self.url, {"rating": 4, "comment": "Sweet dog, pulls on the leash"}
        )
        self.login(self.owner)
        response = self.client.get(self.pet.get_absolute_url())
        self.assertContains(response, "Notes from caregivers")
        self.assertContains(response, "Sweet dog, pulls on the leash")

    def test_next_caregiver_sees_it_on_a_new_request(self):
        self.client.post(
            self.url, {"rating": 4, "comment": "Sweet dog, pulls on the leash"}
        )
        next_user = User.objects.create_user("dana", password="pass12345")
        next_carer = CaregiverProfile.objects.create(
            user=next_user, name="Dana", service_area="Queens"
        )
        start = timezone.now() + timedelta(days=3)
        Booking.objects.create(
            owner=self.owner,
            pet=self.pet,
            caregiver=next_carer,
            service_type=ServiceType.objects.get(name="Dog walking"),
            start_time=start,
            end_time=start + timedelta(hours=1),
        )
        self.login(next_user)
        response = self.client.get(reverse("bookings:caregiver_requests"))
        self.assertContains(response, "From other caregivers")
        self.assertContains(response, "Sweet dog, pulls on the leash")

    def test_only_one_review_per_booking(self):
        self.client.post(self.url, {"rating": 4})
        self.client.post(self.url, {"rating": 2})
        self.assertEqual(Review.objects.count(), 1)

    def test_owner_and_caregiver_each_review_once(self):
        self.client.post(self.url, {"rating": 4})
        self.login(self.owner)
        self.client.post(self.url, {"rating": 5})
        self.assertEqual(
            sorted(Review.objects.values_list("role", flat=True)),
            ["caregiver", "owner"],
        )


class ReviewAccessTests(ReviewTestData):
    def test_someone_else_cannot_review_the_booking(self):
        self.login(User.objects.create_user("sam", password="pass12345"))
        self.assertEqual(self.client.post(self.url, {"rating": 1}).status_code, 404)
        self.assertFalse(Review.objects.exists())

    def test_login_required(self):
        response = self.client.post(self.url, {"rating": 5})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.exists())

    def test_profiles_say_when_there_are_no_reviews(self):
        self.login(self.owner)
        self.assertContains(
            self.client.get(reverse("caregiver", args=[self.caregiver.pk])),
            "Chloe Shih has no reviews yet.",
        )
        self.assertContains(
            self.client.get(self.pet.get_absolute_url()),
            "No caregiver has reviewed Biscuit yet.",
        )

    def test_str(self):
        review = Review.objects.create(
            booking=self.booking, author=self.owner, role="owner", rating=5
        )
        self.assertIn("5★", str(review))
