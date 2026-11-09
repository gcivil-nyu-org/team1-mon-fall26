"""Kat's "PawPal - Report" Figma: reporting from Messages through a menu and a
pop-up, the "Reported" tag, and the admin page's names and banners."""

from django.urls import reverse

from reports.models import Report

from .test_report_content import ReportTestData

POPUP = {"X-Requested-With": "fetch"}


class ReportPopupTests(ReportTestData):
    def setUp(self):
        self.client.force_login(self.owner)
        self.url = self.message_url(self.their_message)

    def test_popup_gets_just_the_card(self):
        response = self.client.get(self.url, headers=POPUP)
        self.assertContains(response, "Report message")
        self.assertContains(response, "Chloe Shih")
        self.assertContains(response, "“Send me money first.”")
        self.assertContains(response, "More details")
        self.assertContains(response, 'placeholder="Anything else we should know?"')
        self.assertNotContains(response, "<html")

    def test_missing_reason_shows_the_error_in_the_popup(self):
        response = self.client.post(self.url, {"details": ""}, headers=POPUP)
        self.assertContains(response, "Choose a reason.")
        self.assertNotContains(response, "<html")
        self.assertFalse(Report.objects.exists())

    def test_sent_report_shows_report_sent(self):
        response = self.client.post(self.url, {"reason": "spam"}, headers=POPUP)
        self.assertContains(response, "Report sent")
        self.assertContains(response, "Our team will review it.")
        self.assertTrue(Report.objects.filter(message=self.their_message).exists())

    def test_reporting_again_in_the_popup_says_so(self):
        self.client.post(self.url, {"reason": "spam"}, headers=POPUP)
        response = self.client.get(self.url, headers=POPUP)
        self.assertContains(response, "already reported this")


class MessagesMenuTests(ReportTestData):
    def setUp(self):
        self.client.force_login(self.owner)
        self.url = self.conversation.get_absolute_url()

    def test_their_messages_open_the_menu(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="bubble-menu"')
        self.assertContains(response, "Copy text")
        self.assertContains(response, 'id="report-dialog"')
        # One menu target: only the other person's message, not my own.
        self.assertContains(response, 'aria-haspopup="menu"', count=1)
        self.assertContains(response, self.message_url(self.their_message))
        self.assertNotContains(response, self.message_url(self.my_message))

    def test_reported_message_gets_a_tag(self):
        Report.objects.create(
            reporter=self.owner,
            reported_user=self.sitter,
            kind="message",
            message=self.their_message,
            content_text=self.their_message.body,
            reason="spam",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "data-reported")
        self.assertContains(response, "Reported</span>")


class AdminInitialsTests(ReportTestData):
    def test_first_name_only_gets_two_letters(self):
        self.stranger.first_name = "Admin"
        self.stranger.save()
        self.client.force_login(self.stranger)
        response = self.client.get(reverse("home"), follow=True)
        self.assertContains(response, ">AD</span>")
