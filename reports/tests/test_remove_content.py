"""Story #97: admins can remove reported content that breaks the rules.

Removed content is hidden from users but stays visible (crossed out) to admins.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import ServiceType
from messaging.models import Message
from reports.models import Report
from reviews.models import Review

from .test_admin_reports import AdminReportsTestData


class RemoveReportedContentTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def remove_url(self, report):
        return reverse("reports:admin_remove", args=[report.pk])

    def remove(self, report):
        return self.client.post(self.remove_url(report), follow=True)

    def test_open_report_has_a_remove_button(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report))
        self.assertContains(
            response, 'class="btn btn-danger" href="?confirm=remove">Remove message</a>'
        )

    def test_confirm_popup(self):
        report = self.report(self.stranger, self.owner_review)
        response = self.client.get(self.detail_url(report), {"confirm": "remove"})
        self.assertContains(response, "Remove this review?")
        self.assertContains(
            response,
            "Users won&#x27;t see it anymore. The report will close as Removed.",
        )
        self.assertContains(
            response, 'class="btn btn-danger" autofocus>Remove</button>'
        )
        self.assertIsNone(Review.objects.get(pk=self.owner_review.pk).removed_at)

    def test_removing_a_message_hides_it_from_users(self):
        report = self.report(self.owner, self.their_message)
        response = self.remove(report)
        self.assertRedirects(response, self.detail_url(report) + "?done=removed")
        self.assertContains(response, "Message removed and moved to Resolved.")
        self.assertContains(response, "report-status-resolved")
        self.assertContains(response, '<p class="report-bubble is-removed">')
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.RESOLVED)
        self.assertEqual(report.handled_by, self.admin)
        self.their_message.refresh_from_db()
        self.assertIsNotNone(self.their_message.removed_at)

        # Both people in the conversation stop seeing it.
        chat = self.conversation.get_absolute_url()
        for user in (self.owner, self.sitter):
            self.client.force_login(user)
            response = self.client.get(chat)
            self.assertNotContains(response, "Send me money first.")
            self.assertContains(response, "Hi Chloe!")

    def test_removed_message_is_not_the_inbox_preview_or_unread(self):
        report = self.report(self.owner, self.their_message)
        self.my_message.delete()
        self.remove(report)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("messaging:inbox"))
        self.assertNotContains(response, "Send me money first.")
        self.assertEqual(response.context["unread_message_count"], 0)
        latest = self.client.get(
            reverse("messaging:latest", args=[self.conversation.pk])
        ).json()
        self.assertEqual(latest["latest_id"], 0)

    def test_removed_message_cannot_be_reported_again(self):
        report = self.report(self.owner, self.their_message)
        self.remove(report)
        self.client.force_login(self.sitter)
        response = self.client.get(
            reverse("reports:message", args=[self.their_message.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_removing_a_review_hides_it_and_its_rating(self):
        first = self.report(self.stranger, self.owner_review)
        second = self.report(self.sitter, self.owner_review)
        response = self.remove(first)
        self.assertContains(response, "Review removed and moved to Resolved.")
        self.assertContains(response, '<p class="is-removed">Great visit!</p>')
        for report in (first, second):
            report.refresh_from_db()
            self.assertEqual(report.status, Report.Status.RESOLVED)
        profile = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertNotContains(profile, "Great visit!")
        self.assertEqual(profile.context["reviews"].count(), 0)

    def test_author_sees_their_review_was_removed_and_cannot_post_again(self):
        report = self.report(self.stranger, self.owner_review)
        self.remove(report)
        self.client.force_login(self.owner)
        response = self.client.get(self.booking.get_absolute_url())
        self.assertContains(response, "PawPal removed your review")
        self.assertNotContains(response, "Rate this visit")
        response = self.client.get(
            reverse("reviews:create", args=[self.booking.pk]), follow=True
        )
        self.assertContains(response, "You&#x27;ve already reviewed this booking.")
        self.assertEqual(
            self.client.get(
                reverse("reviews:thanks", args=[self.owner_review.pk])
            ).status_code,
            404,
        )

    def test_removed_caregiver_review_leaves_the_pet_page(self):
        report = self.report(self.owner, self.sitter_review)
        self.remove(report)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("pets:detail", args=[self.pet.pk]))
        self.assertNotContains(response, "Rude owner, never again.")

    def test_other_reviews_still_show(self):
        start = timezone.now() - timedelta(days=9)
        other_booking = Booking.objects.create(
            owner=self.stranger,
            pet=self.pet,
            caregiver=self.caregiver,
            service_type=ServiceType.objects.get(name="Drop-in visit"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=Booking.Status.COMPLETED,
        )
        Review.objects.create(
            booking=other_booking,
            author=self.stranger,
            role=Review.Role.OWNER,
            rating=4,
            comment="Lovely.",
        )
        self.remove(self.report(self.sitter, self.owner_review))
        profile = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertContains(profile, "Lovely.")
        self.assertNotContains(profile, "Great visit!")

    def test_removing_after_dismissing_is_refused(self):
        report = self.report(self.owner, self.their_message, status="dismissed")
        response = self.remove(report)
        self.assertContains(response, "This report was already handled.")
        self.their_message.refresh_from_db()
        self.assertIsNone(self.their_message.removed_at)

    def test_content_already_deleted_just_closes_the_report(self):
        report = self.report(self.owner, self.their_message)
        self.their_message.delete()
        self.remove(report)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.RESOLVED)

    def test_only_admins_can_remove(self):
        report = self.report(self.owner, self.their_message)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.remove_url(report)).status_code, 403)
        self.assertIsNone(Message.objects.get(pk=self.their_message.pk).removed_at)
