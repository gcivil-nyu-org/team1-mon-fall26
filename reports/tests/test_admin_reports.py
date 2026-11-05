"""Story #95: admins can view all open reports and the reasons given."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from reports.models import Report

from .test_report_content import ReportTestData

User = get_user_model()
LIST_URL = reverse("reports:admin_list")


class AdminReportsTestData(ReportTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_user(
            "admin", password="pw-12345!", first_name="Ada", is_staff=True
        )

    def report(self, reporter, target, reason="spam", status="open", details=""):
        kind = "review" if target.__class__.__name__ == "Review" else "message"
        author = target.author if kind == "review" else target.sender
        text = target.comment if kind == "review" else target.body
        return Report.objects.create(
            reporter=reporter,
            reported_user=author,
            kind=kind,
            **{kind: target},
            content_text=text,
            reason=reason,
            details=details,
            status=status,
        )

    def detail_url(self, report):
        return reverse("reports:admin_detail", args=[report.pk])


class AdminAccessTests(AdminReportsTestData):
    def test_signed_out_visitors_go_to_login(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_regular_users_are_refused(self):
        report = self.report(self.owner, self.their_message)
        for user in (self.owner, self.sitter):
            self.client.force_login(user)
            self.assertEqual(self.client.get(LIST_URL).status_code, 403)
            self.assertEqual(self.client.get(self.detail_url(report)).status_code, 403)

    def test_reports_tab_only_for_admins(self):
        page = reverse("pets:list")
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(page), LIST_URL)
        self.client.force_login(self.admin)
        response = self.client.get(LIST_URL)
        self.assertContains(
            response, f'<a href="{LIST_URL}" class="active">Reports</a>'
        )


class AdminReportListTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_lists_open_reports_with_reasons(self):
        self.report(self.owner, self.their_message, reason="harassment")
        self.report(self.stranger, self.owner_review, reason="fake", details="Fake.")
        response = self.client.get(LIST_URL)
        self.assertContains(response, "Harassment or abusive language")
        self.assertContains(response, "Fake or misleading")
        self.assertContains(response, "Send me money first.")
        self.assertContains(response, "Written by Chloe Shih")
        self.assertContains(response, "reported by Kat Wong")
        self.assertContains(response, 'class="report-kind report-kind-message"')

    def test_only_open_reports_by_default(self):
        self.report(self.owner, self.their_message, status="dismissed")
        response = self.client.get(LIST_URL)
        self.assertNotContains(response, "Send me money first.")
        self.assertContains(response, "No open reports.")

    def test_tabs_filter_and_count(self):
        self.report(self.owner, self.their_message)
        self.report(self.stranger, self.owner_review, status="dismissed")
        self.report(self.sitter, self.owner_review, status="resolved")
        response = self.client.get(LIST_URL, {"status": "dismissed"})
        self.assertContains(response, "Great visit!")
        self.assertNotContains(response, "Send me money first.")
        tabs = {tab["status"]: tab["count"] for tab in response.context["tabs"]}
        self.assertEqual(tabs, {"open": 1, "dismissed": 1, "resolved": 1, "all": 3})
        everything = self.client.get(LIST_URL, {"status": "all"})
        self.assertEqual(len(everything.context["reports"]), 3)

    def test_unknown_tab_falls_back_to_open(self):
        response = self.client.get(LIST_URL, {"status": "nope"})
        self.assertEqual(response.context["status"], "open")

    def test_newest_first(self):
        first = self.report(self.owner, self.their_message)
        second = self.report(self.stranger, self.owner_review)
        reports = self.client.get(LIST_URL).context["reports"]
        self.assertEqual(reports, [second, first])

    def test_content_reported_by_several_people_is_flagged(self):
        self.report(self.stranger, self.owner_review)
        self.report(self.sitter, self.owner_review)
        self.report(self.owner, self.their_message)
        response = self.client.get(LIST_URL)
        self.assertContains(response, "Reported 2 times", count=2)

    def test_deleted_content_still_listed(self):
        report = self.report(self.owner, self.their_message)
        self.their_message.delete()
        response = self.client.get(LIST_URL)
        self.assertContains(response, "Send me money first.")
        self.assertEqual(response.context["reports"][0].times_reported, 1)
        detail = self.client.get(self.detail_url(report))
        self.assertContains(detail, "has since been deleted")


class AdminReportDetailTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_shows_the_content_reason_and_note(self):
        report = self.report(
            self.stranger, self.owner_review, reason="fake", details="Never booked."
        )
        response = self.client.get(self.detail_url(report))
        self.assertContains(response, "Fake or misleading")
        self.assertContains(response, "Great visit!")
        self.assertContains(response, "Never booked.")
        self.assertContains(response, "Review by Kat Wong (kat)")
        self.assertContains(response, reverse("caregiver", args=[self.caregiver.pk]))

    def test_lists_other_reports_of_the_same_content(self):
        report = self.report(self.stranger, self.owner_review)
        self.report(self.sitter, self.owner_review, reason="harassment")
        response = self.client.get(self.detail_url(report))
        self.assertContains(response, "Also reported by")
        self.assertContains(response, "Chloe Shih: Harassment or abusive language")

    def test_message_report_has_no_public_link(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report))
        self.assertIsNone(response.context["where"])
        self.assertNotContains(response, "Also reported by")

    def test_missing_report_is_404(self):
        self.assertEqual(
            self.client.get(reverse("reports:admin_detail", args=[999])).status_code,
            404,
        )
