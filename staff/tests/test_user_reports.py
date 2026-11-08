"""The Users page shows how often an account was reported and its latest
report, linked to the Reports page (#95), as in Kat's Figma."""

from django.urls import reverse

from reports.models import Report

from .test_user_list import StaffTestData, detail_url


class AccountReportsTests(StaffTestData):
    def report(self, reason=Report.Reason.HARASSMENT, **fields):
        return Report.objects.create(
            reporter=self.owner,
            reported_user=self.sitter,
            kind=Report.Kind.MESSAGE,
            content_text="Your loss.",
            reason=reason,
            **fields,
        )

    def test_count_and_latest_report(self):
        self.report(Report.Reason.SPAM, status=Report.Status.DISMISSED)
        latest = self.report()
        response = self.client.get(detail_url(self.sitter))
        self.assertEqual(response.context["report_count"], 2)
        self.assertEqual(response.context["latest_report"], latest)
        self.assertContains(response, "<dt>Reports</dt><dd>2</dd>", html=True)
        self.assertContains(response, "Latest report")
        self.assertContains(response, "Rude or harassing · Today")
        self.assertContains(
            response,
            f'href="{reverse("reports:admin_detail", args=[latest.pk])}">View reports',
        )

    def test_resolved_latest_report_says_how_it_ended(self):
        self.report(status=Report.Status.RESOLVED)
        response = self.client.get(detail_url(self.sitter))
        self.assertContains(response, "· Removed")

    def test_reports_made_by_the_account_dont_count(self):
        self.report()
        response = self.client.get(detail_url(self.owner))
        self.assertEqual(response.context["report_count"], 0)
        self.assertNotContains(response, "Latest report")
