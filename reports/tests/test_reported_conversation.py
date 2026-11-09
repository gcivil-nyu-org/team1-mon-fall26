"""Story #96: for a reported message, admins see the conversation around it."""

from django.utils import timezone

from messaging.models import Message

from .test_admin_reports import AdminReportsTestData


class ReportedConversationTests(AdminReportsTestData):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_shows_every_message_in_order(self):
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report))
        self.assertContains(response, "<h3>Conversation</h3>")
        self.assertEqual(
            list(response.context["conversation"]),
            [self.their_message, self.my_message],
        )
        self.assertContains(response, "Send me money first.")
        self.assertContains(response, "Hi Chloe!")

    def test_highlights_the_reported_message_and_the_reporters_side(self):
        report = self.report(self.owner, self.their_message)
        html = self.client.get(self.detail_url(report)).content.decode()
        self.assertIn('<li class="report-line is-reported">', html)
        # The reporter's own messages sit on the right, like in Messages.
        self.assertIn('<li class="report-line is-reporter">', html)
        self.assertEqual(html.count('class="report-tag"'), 1)

    def test_removed_messages_still_show_crossed_out(self):
        report = self.report(self.owner, self.their_message)
        Message.objects.filter(pk=self.my_message.pk).update(removed_at=timezone.now())
        response = self.client.get(self.detail_url(report))
        self.assertContains(
            response, '<p class="report-bubble is-removed">Hi Chloe!</p>'
        )
        self.assertContains(response, "Removed</span>")

    def test_other_conversations_are_not_shown(self):
        other = Message.objects.create(
            conversation=self.conversation.__class__.objects.create(
                owner=self.stranger, caregiver=self.caregiver
            ),
            sender=self.stranger,
            body="A different chat.",
        )
        report = self.report(self.owner, self.their_message)
        response = self.client.get(self.detail_url(report))
        self.assertNotIn(other, list(response.context["conversation"]))
        self.assertNotContains(response, "A different chat.")

    def test_review_reports_have_no_conversation(self):
        report = self.report(self.stranger, self.owner_review)
        response = self.client.get(self.detail_url(report))
        self.assertNotIn("conversation", response.context)
        self.assertNotContains(response, "<h3>Conversation</h3>")
