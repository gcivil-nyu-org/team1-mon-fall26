"""Story #98: admins can dismiss a report when the content is fine."""

from django.urls import reverse

from reports.models import Report

from .test_admin_reports import AdminReportsTestData


class DismissReportTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def dismiss_url(self, report):
        return reverse("reports:admin_dismiss", args=[report.pk])

    def test_open_report_has_a_dismiss_button(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report))
        self.assertContains(response, 'href="?confirm=dismiss">Dismiss report</a>')
        self.assertNotContains(response, 'role="dialog"')

    def test_confirm_popup_shows_the_content(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report), {"confirm": "dismiss"})
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "Dismiss this report?")
        self.assertContains(
            response, "The message stays up. The report will close as Dismissed."
        )
        self.assertContains(response, "“Send me money first.”")
        self.assertContains(response, f'action="{self.dismiss_url(report)}"')
        self.assertTrue(Report.objects.get().is_open)

    def test_unknown_confirm_is_ignored(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report), {"confirm": "nope"})
        self.assertNotContains(response, 'role="dialog"')

    def test_dismissing_moves_the_report_to_resolved(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.post(self.dismiss_url(report), follow=True)
        self.assertRedirects(response, self.detail_url(report) + "?done=dismissed")
        self.assertContains(response, "Report dismissed and moved to Resolved.")
        self.assertContains(response, "report-done is-dismissed")
        # Figma: stay on Open, without the report just dismissed in the list.
        self.assertEqual(response.context["tab"], "open")
        self.assertNotIn(report, response.context["reports"])
        self.assertContains(response, "report-status-dismissed")
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.DISMISSED)
        self.assertEqual(report.handled_by, self.admin)
        self.assertIsNotNone(report.handled_at)
        # The message stays up.
        self.their_message.refresh_from_db()
        # Opened again later: a gray banner says who handled it (Figma).
        later = self.client.get(self.detail_url(report))
        self.assertContains(later, "Dismissed by Ada · Today,")
        self.assertNotContains(response, "?confirm=dismiss")

    def test_dismissing_closes_every_open_report_about_the_same_content(self):
        first = self.report(self.stranger, self.owner_review)
        self.report(self.sitter, self.owner_review)
        other = self.report(self.owner, self.their_message)
        self.client.post(self.dismiss_url(first))
        self.assertEqual(
            Report.objects.filter(review=self.owner_review, status="dismissed").count(),
            2,
        )
        other.refresh_from_db()
        self.assertTrue(other.is_open)

    def test_handled_report_cannot_be_dismissed_again(self):
        report = self.report(self.owner, self.their_message, status="resolved")
        response = self.client.post(self.dismiss_url(report), follow=True)
        self.assertRedirects(response, self.detail_url(report))
        self.assertContains(response, "This report was already handled.")
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.RESOLVED)
        # No popup or button for handled reports either.
        response = self.client.get(self.detail_url(report), {"confirm": "dismiss"})
        self.assertNotContains(response, 'role="dialog"')
        self.assertNotContains(response, "Dismiss report</a>")

    def test_report_on_deleted_content_can_still_be_dismissed(self):
        report = self.report(self.owner, self.their_message)
        self.their_message.delete()
        self.client.post(self.dismiss_url(report))
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.DISMISSED)

    def test_dismiss_needs_post(self):
        report = self.report(self.owner, self.their_message)
        self.assertEqual(self.client.get(self.dismiss_url(report)).status_code, 405)

    def test_only_admins_can_dismiss(self):
        report = self.report(self.owner, self.their_message)
        self.client.force_login(self.sitter)
        self.assertEqual(self.client.post(self.dismiss_url(report)).status_code, 403)
        report.refresh_from_db()
        self.assertTrue(report.is_open)

    def test_tabs_work_from_a_handled_report(self):
        # Dismiss, go to Resolved, then back to Open: the tabs must switch.
        report = self.report(self.owner, self.their_message)
        response = self.client.post(self.dismiss_url(report), follow=True)
        list_url = reverse("reports:admin_list")
        self.assertContains(response, f'href="{list_url}?status=resolved"')
        resolved = self.client.get(list_url, {"status": "resolved"})
        self.assertEqual(resolved.context["tab"], "resolved")
        self.assertContains(resolved, f'href="{list_url}?status=open"')
        back = self.client.get(list_url, {"status": "open"})
        self.assertEqual(back.context["tab"], "open")
