"""#99 Remove Inappropriate Reviews: admins remove a review straight from an
account's review history (#100), without waiting for a report."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from reports.models import Report
from reviews.models import Review

from .test_review_history import ReviewHistoryData
from .test_user_list import detail_url


def remove_url(account, review):
    return reverse("staff:remove_review", args=[account.pk, review.pk])


class RemoveReviewTests(ReviewHistoryData):
    def test_reviews_that_are_up_have_a_remove_button(self):
        response = self.client.get(detail_url(self.owner))
        self.assertContains(response, f"remove_review={self.kat_review.pk}")
        # The removed one doesn't.
        self.assertNotContains(response, f"remove_review={self.chloe_review.pk}")

    def test_remove_asks_for_confirmation_first(self):
        response = self.client.get(
            detail_url(self.owner) + f"?remove_review={self.kat_review.pk}"
        )
        self.assertContains(response, "Remove this review?")
        self.assertContains(response, "Chloe was wonderful with Miso.")
        self.assertContains(
            response, f'action="{remove_url(self.owner, self.kat_review)}"'
        )
        self.kat_review.refresh_from_db()
        self.assertIsNone(self.kat_review.removed_at)

    def test_no_popup_for_a_review_outside_the_history_or_already_removed(self):
        for pk in (self.chloe_review.pk, 999, "abc"):
            response = self.client.get(detail_url(self.new) + f"?remove_review={pk}")
            self.assertNotContains(response, "Remove this review?")
        response = self.client.get(
            detail_url(self.owner) + f"?remove_review={self.chloe_review.pk}"
        )
        self.assertNotContains(response, "Remove this review?")

    def test_removing_hides_the_review_and_shows_a_banner(self):
        response = self.client.post(
            remove_url(self.owner, self.kat_review), follow=True
        )
        self.assertRedirects(response, detail_url(self.owner) + "?done=review_removed")
        self.assertContains(response, "Review removed. Users won’t see it anymore.")
        self.kat_review.refresh_from_db()
        self.assertIsNotNone(self.kat_review.removed_at)
        self.assertNotIn(self.kat_review, Review.objects.visible())
        # It's hidden on the caregiver's public profile too.
        self.client.force_login(self.owner)
        profile = self.client.get(
            reverse("caregiver", args=[self.sitter.caregiver_profile.pk])
        )
        self.assertNotContains(profile, "Chloe was wonderful with Miso.")

    def test_removing_closes_open_reports_about_it(self):
        reporter = get_user_model().objects.create_user("nano")
        report = Report.objects.create(
            reporter=reporter,
            reported_user=self.owner,
            kind=Report.Kind.REVIEW,
            review=self.kat_review,
            content_text=self.kat_review.comment,
            reason=Report.Reason.FAKE,
        )
        self.client.post(remove_url(self.owner, self.kat_review))
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.RESOLVED)
        self.assertEqual(report.handled_by, self.admin)

    def test_removing_twice_keeps_the_first_time(self):
        when = self.chloe_review.removed_at
        response = self.client.post(remove_url(self.owner, self.chloe_review))
        self.assertRedirects(response, detail_url(self.owner))
        self.chloe_review.refresh_from_db()
        self.assertEqual(self.chloe_review.removed_at, when)

    def test_review_must_be_in_that_accounts_history(self):
        response = self.client.post(remove_url(self.new, self.kat_review))
        self.assertEqual(response.status_code, 404)
        self.kat_review.refresh_from_db()
        self.assertIsNone(self.kat_review.removed_at)

    def test_only_admins_can_remove(self):
        self.client.force_login(self.sitter)
        response = self.client.post(remove_url(self.owner, self.kat_review))
        self.assertEqual(response.status_code, 403)
        self.kat_review.refresh_from_db()
        self.assertIsNone(self.kat_review.removed_at)

    def test_remove_needs_a_post(self):
        response = self.client.get(remove_url(self.owner, self.kat_review))
        self.assertEqual(response.status_code, 405)

    def test_banner_only_after_removing(self):
        self.assertNotContains(
            self.client.get(detail_url(self.owner)), "Review removed."
        )
