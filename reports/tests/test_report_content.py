"""Story #117: pet owners and caregivers can report an inappropriate review or
a message they received, so admins can review it."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import CaregiverProfile, ServiceType
from messaging.models import Conversation, Message
from pets.models import Pet, PetType
from reports.forms import ReportForm
from reports.models import MAX_DETAILS_LENGTH, Report
from reviews.models import Review

User = get_user_model()


class ReportTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "kat", password="pw-12345!", first_name="Kat", last_name="Wong"
        )
        cls.sitter = User.objects.create_user(
            "chloe", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        cls.stranger = User.objects.create_user("nano", password="pw-12345!")
        cls.caregiver = CaregiverProfile.objects.create(
            user=cls.sitter, name="Chloe Shih", service_area="Park Slope"
        )
        cls.pet = Pet.objects.create(
            owner=cls.owner, name="Miso", pet_type=PetType.objects.get(name="Cat")
        )
        start = timezone.now() - timedelta(days=3)
        cls.booking = Booking.objects.create(
            owner=cls.owner,
            pet=cls.pet,
            caregiver=cls.caregiver,
            service_type=ServiceType.objects.get(name="Drop-in visit"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=Booking.Status.COMPLETED,
        )
        # The caregiver's review of the owner and pet, shown on the pet's page.
        cls.sitter_review = Review.objects.create(
            booking=cls.booking,
            author=cls.sitter,
            role=Review.Role.CAREGIVER,
            rating=1,
            comment="Rude owner, never again.",
        )
        # The owner's review of the caregiver, shown on the caregiver's profile.
        cls.owner_review = Review.objects.create(
            booking=cls.booking,
            author=cls.owner,
            role=Review.Role.OWNER,
            rating=5,
            comment="Great visit!",
        )
        cls.conversation = Conversation.objects.create(
            owner=cls.owner, caregiver=cls.caregiver
        )
        cls.their_message = Message.objects.create(
            conversation=cls.conversation,
            sender=cls.sitter,
            body="Send me money first.",
        )
        cls.my_message = Message.objects.create(
            conversation=cls.conversation, sender=cls.owner, body="Hi Chloe!"
        )

    def review_url(self, review):
        return reverse("reports:review", args=[review.pk])

    def message_url(self, message):
        return reverse("reports:message", args=[message.pk])


class ReportReviewTests(ReportTestData):
    def test_login_required(self):
        response = self.client.get(self.review_url(self.owner_review))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_form_shows_the_review_and_the_reasons(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.review_url(self.sitter_review))
        self.assertContains(response, "Report review")
        self.assertContains(response, "Chloe Shih")
        self.assertContains(response, "Rude owner, never again.")
        for _, label in Report.Reason.choices:
            self.assertContains(response, label)
        # Figma "Report Message": no anonymity line, a Submit report button.
        self.assertContains(response, "Submit report")

    def test_form_shows_which_review_it_is(self):
        # The visit it's about and its paws, so a rating-only review is clear too.
        self.sitter_review.comment = ""
        self.sitter_review.save()
        self.client.force_login(self.owner)
        response = self.client.get(self.review_url(self.sitter_review))
        when = timezone.localtime(self.booking.start_time).strftime("%b %-d")
        self.assertContains(response, f"Miso · Drop-in visit · {when}")
        self.assertContains(response, 'aria-label="Rated 1 out of 5"')
        self.assertContains(response, "No written review, rating only.")
        self.assertNotContains(response, "(Rating only, no written review)")

    def test_reporting_a_review_saves_an_open_report(self):
        self.client.force_login(self.owner)
        back = reverse("pets:detail", args=[self.pet.pk])
        response = self.client.post(
            self.review_url(self.sitter_review),
            {"reason": "harassment", "details": "Not true.", "next": back},
            follow=True,
        )
        self.assertRedirects(response, back)
        self.assertContains(response, "Thanks for letting us know.")
        report = Report.objects.get()
        self.assertEqual(report.kind, Report.Kind.REVIEW)
        self.assertEqual(report.review, self.sitter_review)
        self.assertEqual(report.reporter, self.owner)
        self.assertEqual(report.reported_user, self.sitter)
        self.assertEqual(report.reason, Report.Reason.HARASSMENT)
        self.assertEqual(report.details, "Not true.")
        self.assertEqual(report.content_text, "Rude owner, never again.")
        self.assertEqual(report.status, Report.Status.OPEN)

    def test_without_next_it_goes_back_to_the_caregiver_profile(self):
        self.client.force_login(self.stranger)
        response = self.client.post(
            self.review_url(self.owner_review), {"reason": "fake"}
        )
        self.assertRedirects(
            response,
            reverse("caregiver", args=[self.caregiver.pk]),
            fetch_redirect_response=False,
        )

    def test_unsafe_next_is_ignored(self):
        self.client.force_login(self.stranger)
        response = self.client.post(
            self.review_url(self.owner_review),
            {"reason": "spam", "next": "https://evil.example.com/"},
        )
        self.assertEqual(response.url, reverse("caregiver", args=[self.caregiver.pk]))

    def test_cannot_report_your_own_review(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self.review_url(self.owner_review), {"reason": "spam"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Report.objects.exists())

    def test_reporting_twice_keeps_one_report(self):
        self.client.force_login(self.stranger)
        self.client.post(self.review_url(self.owner_review), {"reason": "spam"})
        response = self.client.post(
            self.review_url(self.owner_review), {"reason": "fake"}, follow=True
        )
        self.assertContains(response, "already reported this")
        self.assertEqual(Report.objects.count(), 1)

    def test_a_reason_is_required(self):
        self.client.force_login(self.stranger)
        response = self.client.post(self.review_url(self.owner_review), {})
        self.assertContains(response, "Choose a reason.")
        self.assertFalse(Report.objects.exists())

    def test_missing_review_is_404(self):
        self.client.force_login(self.stranger)
        response = self.client.get(reverse("reports:review", args=[999]))
        self.assertEqual(response.status_code, 404)

    def test_report_link_shows_on_other_peoples_reviews_only(self):
        profile = reverse("caregiver", args=[self.caregiver.pk])
        self.client.force_login(self.stranger)
        self.assertContains(
            self.client.get(profile), self.review_url(self.owner_review)
        )
        # The author doesn't get a Report link on their own review.
        self.client.force_login(self.owner)
        self.assertNotContains(
            self.client.get(profile), self.review_url(self.owner_review)
        )

    def test_owner_can_report_a_review_of_their_pet_from_the_pet_page(self):
        self.client.force_login(self.owner)
        page = reverse("pets:detail", args=[self.pet.pk])
        response = self.client.get(page)
        self.assertContains(response, self.review_url(self.sitter_review))
        self.assertContains(response, f"?next={page}")


class ReportMessageTests(ReportTestData):
    def test_reporting_a_message_you_received(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self.message_url(self.their_message),
            {"reason": "spam", "details": "Asked for money."},
        )
        self.assertRedirects(
            response,
            self.conversation.get_absolute_url(),
            fetch_redirect_response=False,
        )
        report = Report.objects.get()
        self.assertEqual(report.kind, Report.Kind.MESSAGE)
        self.assertEqual(report.message, self.their_message)
        self.assertEqual(report.reported_user, self.sitter)
        self.assertEqual(report.content_text, "Send me money first.")

    def test_form_shows_the_message(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.message_url(self.their_message))
        self.assertContains(response, "Report message")
        self.assertContains(response, "Chloe Shih")
        self.assertContains(response, "Send me money first.")

    def test_cannot_report_your_own_message(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.message_url(self.my_message))
        self.assertEqual(response.status_code, 404)

    def test_people_outside_the_conversation_cannot_see_or_report_it(self):
        self.client.force_login(self.stranger)
        response = self.client.post(
            self.message_url(self.their_message), {"reason": "spam"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Report.objects.exists())

    def test_report_link_shows_on_received_messages_only(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.conversation.get_absolute_url())
        self.assertContains(response, self.message_url(self.their_message))
        self.assertNotContains(response, self.message_url(self.my_message))

    def test_the_caregiver_can_report_the_owners_message(self):
        self.client.force_login(self.sitter)
        self.client.post(self.message_url(self.my_message), {"reason": "inappropriate"})
        self.assertEqual(Report.objects.get().reported_user, self.owner)


class ReportFormAndModelTests(ReportTestData):
    def test_details_are_optional_for_every_reason(self):
        # "More details" says Optional, so it is, even for Something else.
        for reason, _ in Report.Reason.choices:
            self.assertTrue(ReportForm({"reason": reason, "details": ""}).is_valid())
        self.assertTrue(ReportForm({"reason": "other", "details": "Spam."}).is_valid())

    def test_details_have_a_length_limit(self):
        form = ReportForm({"reason": "spam", "details": "x" * (MAX_DETAILS_LENGTH + 1)})
        self.assertFalse(form.is_valid())
        self.assertIn(
            f"Keep it under {MAX_DETAILS_LENGTH} characters.", form.errors["details"]
        )

    def test_report_survives_when_the_content_is_deleted(self):
        report = Report.objects.create(
            reporter=self.owner,
            reported_user=self.sitter,
            kind=Report.Kind.MESSAGE,
            message=self.their_message,
            content_text=self.their_message.body,
            reason=Report.Reason.SPAM,
        )
        self.their_message.delete()
        report.refresh_from_db()
        self.assertIsNone(report.message)
        self.assertEqual(report.content_text, "Send me money first.")

    def test_str(self):
        report = Report(
            reporter=self.owner, reported_user=self.sitter, kind=Report.Kind.REVIEW
        )
        self.assertEqual(str(report), "Review reported by kat (Open)")
