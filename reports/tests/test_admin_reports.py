"""Story #95: admins can view all open reports and the reasons given."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from reports.models import Report
from reviews.templatetags.review_tags import reviewer_name

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

    def test_admin_header_matches_figma(self):
        page = reverse("pets:list")
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(page), LIST_URL)
        self.assertNotContains(self.client.get(page), 'class="admin-badge"')
        self.client.force_login(self.admin)
        response = self.client.get(LIST_URL)
        self.assertContains(response, '<span class="admin-badge">Admin</span>')
        self.assertContains(
            response, f'<a href="{LIST_URL}" class="active">Reports</a>'
        )
        self.assertContains(response, ">Explore</a>")
        self.assertContains(response, "avatar avatar-admin")
        html = response.content.decode()
        self.assertLess(html.index(">Reports</a>"), html.index(">Users</a>"))


class AdminReportListTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_lists_open_reports_and_selects_the_newest(self):
        older = self.report(self.owner, self.their_message, reason="harassment")
        newer = self.report(
            self.stranger, self.owner_review, reason="fake", details="Never booked."
        )
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["reports"], [newer, older])
        self.assertEqual(response.context["selected"], newer)
        self.assertContains(response, "Rude or harassing")
        self.assertContains(response, "Message from Chloe S.")
        self.assertContains(response, "Reported by Kat W.")
        self.assertContains(response, "Review from Kat W.")
        self.assertContains(
            response, 'class="report-status report-status-open"', count=3
        )

    def test_tabs_are_open_and_resolved_with_counts(self):
        self.report(self.owner, self.their_message)
        self.report(self.stranger, self.owner_review, status="dismissed")
        self.report(self.sitter, self.owner_review, status="resolved")
        tabs = {t["key"]: t["count"] for t in self.client.get(LIST_URL).context["tabs"]}
        self.assertEqual(tabs, {"open": 1, "resolved": 2})
        response = self.client.get(LIST_URL, {"status": "resolved"})
        self.assertEqual(len(response.context["reports"]), 2)
        self.assertContains(response, "report-status-dismissed")
        self.assertContains(response, "report-status-resolved")
        self.assertNotContains(response, "Send me money first.")

    def test_unknown_tab_falls_back_to_open(self):
        response = self.client.get(LIST_URL, {"status": "nope"})
        self.assertEqual(response.context["tab"], "open")

    def test_empty_states(self):
        self.assertContains(self.client.get(LIST_URL), "No open reports. Nice!")
        response = self.client.get(LIST_URL, {"status": "resolved"})
        self.assertContains(response, "No resolved reports yet.")
        self.assertIsNone(response.context["selected"])


class AdminReportDetailTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_review_report_shows_the_note_and_review_card(self):
        report = self.report(
            self.stranger, self.owner_review, reason="fake", details="Never booked."
        )
        response = self.client.get(self.detail_url(report))
        self.assertEqual(response.context["selected"], report)
        self.assertContains(response, "Fake or misleading")
        self.assertContains(response, f"Note from {reviewer_name(self.stranger)}")
        self.assertContains(response, "“Never booked.”")
        self.assertContains(response, "Review on Chloe Shih's profile")
        self.assertContains(response, "Great visit!")
        self.assertContains(response, "Posted today")
        self.assertContains(response, 'aria-label="Rated 5 out of 5"')
        self.assertContains(response, "Today, ")

    def test_message_report_shows_the_message(self):
        report = self.report(self.owner, self.their_message, reason="harassment")
        response = self.client.get(self.detail_url(report))
        self.assertContains(response, "Reported message")
        self.assertContains(
            response, '<p class="report-bubble">Send me money first.</p>'
        )
        self.assertNotContains(response, "Note from")

    def test_resolved_report_opens_in_the_resolved_tab(self):
        report = self.report(self.owner, self.their_message, status="dismissed")
        response = self.client.get(self.detail_url(report))
        self.assertEqual(response.context["tab"], "resolved")
        self.assertContains(response, 'class="report-row is-selected"')

    def test_deleted_content_still_shows_the_saved_text(self):
        report = self.report(self.stranger, self.owner_review)
        self.owner_review.delete()
        response = self.client.get(self.detail_url(report))
        self.assertContains(response, "Great visit!")
        self.assertContains(response, "Deleted")
        self.assertContains(response, "Reported review")

    def test_missing_report_is_404(self):
        self.assertEqual(
            self.client.get(reverse("reports:admin_detail", args=[999])).status_code,
            404,
        )
