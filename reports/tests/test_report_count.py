"""#94 Receive Content Reports: the admin header shows how many reports are
open, so admins notice new ones from any page."""

from django.urls import reverse

from reports.models import Report
from reports.templatetags.report_tags import open_report_count

from .test_admin_reports import AdminReportsTestData

BADGE = '<span class="nav-count">'


class ReportCountTests(AdminReportsTestData):
    def test_admins_see_the_open_report_count(self):
        self.report(self.owner, self.their_message)
        self.report(self.stranger, self.sitter_review)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff:user_list"))
        self.assertContains(
            response, f'{BADGE}2<span class="visually-hidden"> open</span>'
        )

    def test_handled_reports_dont_count(self):
        self.report(self.owner, self.their_message, status=Report.Status.DISMISSED)
        self.report(self.stranger, self.sitter_review, status=Report.Status.RESOLVED)
        self.assertEqual(open_report_count(), 0)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:admin_list"))
        self.assertNotContains(response, BADGE)

    def test_new_report_shows_up_in_the_count(self):
        self.assertEqual(open_report_count(), 0)
        self.client.force_login(self.owner)
        self.client.post(
            reverse("reports:message", args=[self.their_message.pk]),
            {"reason": Report.Reason.SPAM},
        )
        self.assertEqual(open_report_count(), 1)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("staff:user_list")), f"{BADGE}1")

    def test_only_admins_see_it(self):
        self.report(self.stranger, self.sitter_review)
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(reverse("pets:list")), BADGE)
