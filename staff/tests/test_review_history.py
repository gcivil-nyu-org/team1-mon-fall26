"""#100 View User Review History: on the admin Users page, the reviews an
account wrote and the reviews about it, including ones an admin removed."""

from datetime import timedelta

from django.utils import timezone

from bookings.models import Booking
from caregivers.models import ServiceType
from pets.models import Pet, PetType
from reviews.models import Review
from staff.accounts import RECENT_REVIEWS, review_history

from .test_user_list import StaffTestData, detail_url


class ReviewHistoryData(StaffTestData):
    """Kat reviewed Chloe, and Chloe's review of Kat and Miso was removed."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        dog = PetType.objects.get_or_create(name="Dog")[0]
        cls.miso = Pet.objects.create(owner=cls.owner, name="Miso", pet_type=dog)
        cls.walking = ServiceType.objects.get_or_create(name="Dog walking")[0]
        cls.booking = cls.book(-3)
        # Kat reviews Chloe; Chloe reviews Kat and Miso.
        cls.kat_review = Review.objects.create(
            booking=cls.booking,
            author=cls.owner,
            role=Review.Role.OWNER,
            rating=5,
            comment="Chloe was wonderful with Miso.",
        )
        cls.chloe_review = Review.objects.create(
            booking=cls.booking,
            author=cls.sitter,
            role=Review.Role.CAREGIVER,
            rating=2,
            comment="Miso pulled on the leash a lot.",
            removed_at=timezone.now(),
        )

    @classmethod
    def book(cls, days):
        start = timezone.now() + timedelta(days=days)
        return Booking.objects.create(
            owner=cls.owner,
            pet=cls.miso,
            caregiver=cls.sitter.caregiver_profile,
            service_type=cls.walking,
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=Booking.Status.COMPLETED,
        )


class ReviewHistoryTests(ReviewHistoryData):
    def test_owner_sees_reviews_written_and_received(self):
        response = self.client.get(detail_url(self.owner))
        self.assertContains(response, "Reviews written")
        self.assertContains(response, "Reviews received")
        # Written: Kat's review of Chloe.
        self.assertContains(response, "About Chloe Shih")
        self.assertContains(response, "Chloe was wonderful with Miso.")
        self.assertContains(response, "Rated 5 out of 5")
        # Received: Chloe's review of Kat and Miso, removed but still listed.
        self.assertContains(response, "From Chloe Shih")
        self.assertContains(response, "Miso pulled on the leash a lot.")
        self.assertContains(response, "staff-review is-removed")
        self.assertContains(response, ">Removed<")

    def test_caregiver_sees_the_same_reviews_the_other_way(self):
        response = self.client.get(detail_url(self.sitter))
        self.assertContains(response, "About Kat W &amp; Miso")
        self.assertContains(response, "From Kat W")
        self.assertContains(response, "Miso · Dog walking")

    def test_rating_only_review(self):
        self.kat_review.comment = ""
        self.kat_review.save()
        response = self.client.get(detail_url(self.owner))
        self.assertContains(response, "Rating only, no written review.")

    def test_no_reviews_yet(self):
        response = self.client.get(detail_url(self.new))
        self.assertContains(response, "No reviews written yet.")
        self.assertContains(response, "No reviews about this account yet.")

    def test_only_the_most_recent_are_listed(self):
        for days in range(RECENT_REVIEWS + 1):
            Review.objects.create(
                booking=self.book(-10 - days),
                author=self.owner,
                role=Review.Role.OWNER,
                rating=4,
            )
        history = review_history(self.owner)
        self.assertEqual(len(history["reviews_written"]), RECENT_REVIEWS)
        self.assertEqual(history["reviews_written_count"], RECENT_REVIEWS + 2)
        response = self.client.get(detail_url(self.owner))
        self.assertContains(
            response, f"The {RECENT_REVIEWS} most recent of {RECENT_REVIEWS + 2}."
        )

    def test_reviews_of_other_accounts_are_not_mixed_in(self):
        history = review_history(self.new)
        self.assertEqual(history["reviews_written_count"], 0)
        self.assertEqual(history["reviews_received_count"], 0)
        # Kat wrote one and received one; the caregiver's own review isn't "received".
        kat = review_history(self.owner)
        self.assertEqual(list(kat["reviews_written"]), [self.kat_review])
        self.assertEqual(list(kat["reviews_received"]), [self.chloe_review])
