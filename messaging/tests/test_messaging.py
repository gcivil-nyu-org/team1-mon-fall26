"""Acceptance tests for View Message History, Message before a Service, and
Inbox + Care Updates (the Figma "PawPal - Message" frames)."""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from bookings.models import Booking
from caregivers.models import CaregiverProfile, ServiceType
from pets.models import Pet, PetType

from ..inbox import booking_state, by_day, counterpart, day_label, unread_count
from ..models import MAX_MESSAGE_LENGTH, Conversation, Message
from ..templatetags.messaging_tags import booking_when, inbox_time

INBOX = reverse("messaging:inbox")
Status = Booking.Status


def conversation_url(conversation):
    return reverse("messaging:conversation", args=[conversation.pk])


def send_url(conversation):
    return reverse("messaging:send", args=[conversation.pk])


class MessagingTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(
            "kat", password="pw-12345!", first_name="Kat", last_name="Wong"
        )
        cls.other_owner = User.objects.create_user("nano", password="pw-12345!")
        cls.sitter = User.objects.create_user(
            "chloe", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        AccountProfile.objects.create(
            user=cls.sitter, role=AccountProfile.Role.CAREGIVER
        )
        cls.caregiver = CaregiverProfile.objects.create(
            name="Chloe Shih",
            service_area="Brooklyn",
            neighborhood="Park Slope",
            user=cls.sitter,
        )
        cls.other_sitter = User.objects.create_user("alicia", password="pw-12345!")
        cls.other_caregiver = CaregiverProfile.objects.create(
            name="Alicia Tian", service_area="Windsor Terrace", user=cls.other_sitter
        )
        cat = PetType.objects.get_or_create(name="Cat")[0]
        cls.pet = Pet.objects.create(owner=cls.owner, name="Miso", pet_type=cat)
        cls.drop_in = ServiceType.objects.get_or_create(name="Drop-in visit")[0]

    def make_booking(self, status=Status.ACCEPTED, start_in=timedelta(hours=-1)):
        start = timezone.now() + start_in
        return Booking.objects.create(
            owner=self.owner,
            pet=self.pet,
            caregiver=self.caregiver,
            service_type=self.drop_in,
            start_time=start,
            end_time=start + timedelta(hours=2),
            status=status,
        )

    def general(self, owner=None, caregiver=None):
        return Conversation.objects.create(
            owner=owner or self.owner, caregiver=caregiver or self.caregiver
        )

    def say(self, conversation, sender, body, when=None):
        when = when or timezone.now()
        message = Message.objects.create(
            conversation=conversation, sender=sender, body=body, created_at=when
        )
        Conversation.objects.filter(pk=conversation.pk).update(last_message_at=when)
        return message


class ConversationModelTests(MessagingTestData):
    def test_one_conversation_without_a_booking_per_owner_and_caregiver(self):
        self.general()
        with self.assertRaises(IntegrityError):
            self.general()

    def test_each_booking_can_also_have_its_own_conversation(self):
        self.general()
        first = Conversation.objects.create(
            owner=self.owner, caregiver=self.caregiver, booking=self.make_booking()
        )
        second = Conversation.objects.create(
            owner=self.owner, caregiver=self.caregiver, booking=self.make_booking()
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertIn("booking #", str(first))
        self.assertIn("no booking", str(self.general(owner=self.other_owner)))

    def test_message_text(self):
        message = self.say(self.general(), self.owner, "Do you take rabbits?")
        self.assertEqual(str(message), "kat: Do you take rabbits?")


class InboxHelperTests(MessagingTestData):
    def test_status_pill(self):
        self.assertIsNone(booking_state(None))
        happening = self.make_booking()
        self.assertEqual(booking_state(happening)["label"], "In progress")
        later = self.make_booking(start_in=timedelta(days=2))
        self.assertEqual(booking_state(later)["label"], "Accepted")
        pending = self.make_booking(Status.PENDING, timedelta(days=2))
        self.assertEqual(booking_state(pending), {"key": "pending", "label": "Pending"})
        done = self.make_booking(Status.COMPLETED)
        self.assertEqual(booking_state(done)["key"], "completed")

    def test_other_person_for_each_side(self):
        conversation = self.general()
        as_owner = counterpart(conversation, self.owner)
        self.assertEqual(as_owner["name"], "Chloe Shih")
        self.assertEqual(as_owner["role"], "Caregiver")
        self.assertEqual(as_owner["place"], "Park Slope")
        self.assertEqual(as_owner["initials"], "CS")
        as_caregiver = counterpart(conversation, self.sitter)
        self.assertEqual(as_caregiver["name"], "Kat W.")
        self.assertEqual(as_caregiver["first_name"], "Kat")
        self.assertEqual(as_caregiver["role"], "Pet owner")
        self.assertEqual(as_caregiver["initials"], "KW")

    def test_day_labels(self):
        now = timezone.now()
        self.assertEqual(day_label(now), "Today")
        self.assertEqual(day_label(now - timedelta(days=1)), "Yesterday")
        ten_days_ago = now - timedelta(days=10)
        expected = r"^[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}"
        if timezone.localtime(ten_days_ago).year != timezone.localdate().year:
            expected += r", \d{4}"
        self.assertRegex(day_label(ten_days_ago), expected + "$")
        old = datetime(2020, 10, 3, 17, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(day_label(old), "Sat, Oct 3, 2020")

    def test_messages_are_grouped_by_day(self):
        conversation = self.general()
        now = timezone.now()
        self.say(conversation, self.owner, "Hi", now - timedelta(days=1))
        self.say(conversation, self.sitter, "Hello", now - timedelta(days=1))
        self.say(conversation, self.owner, "Still free?", now)
        groups = by_day(conversation.messages.all())
        self.assertEqual([g["label"] for g in groups], ["Yesterday", "Today"])
        self.assertEqual(len(groups[0]["messages"]), 2)

    def test_inbox_times(self):
        now = timezone.now()
        self.assertEqual(inbox_time(None), "")
        self.assertRegex(inbox_time(now), r"^\d{1,2}:\d{2} (AM|PM)$")
        self.assertEqual(inbox_time(now - timedelta(days=1)), "Yesterday")
        ten_days_ago = now - timedelta(days=10)
        expected = r"^[A-Z][a-z]{2} \d{1,2}"
        if timezone.localtime(ten_days_ago).year != timezone.localdate().year:
            expected += r", \d{4}"
        self.assertRegex(inbox_time(ten_days_ago), expected + "$")
        self.assertEqual(
            inbox_time(datetime(2020, 9, 24, 15, tzinfo=dt_timezone.utc)),
            "Sep 24, 2020",
        )

    def test_booking_card_time(self):
        self.assertTrue(booking_when(timezone.now()).startswith("Today · "))
        when = datetime(2020, 10, 3, 21, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(booking_when(when), "Sat, Oct 3 · 5:30 PM")

    def test_unread_count(self):
        conversation = self.general()
        self.say(conversation, self.owner, "Hi Chloe!")
        # The sender has read their own message; the caregiver hasn't.
        self.assertEqual(unread_count(self.owner), 0)
        self.assertEqual(unread_count(self.sitter), 1)
        conversation.mark_read(self.sitter)
        self.assertEqual(unread_count(self.sitter), 0)
        self.say(conversation, self.sitter, "Hi Kat!")
        self.assertEqual(unread_count(self.owner), 1)


class MessageBeforeServiceTests(MessagingTestData):
    """Owners can ask a caregiver questions before requesting care."""

    def url(self, caregiver):
        return reverse("messaging:message_caregiver", args=[caregiver.pk])

    def test_login_required(self):
        response = self.client.get(self.url(self.caregiver))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_owner_starts_a_conversation(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url(self.caregiver))
        conversation = Conversation.objects.get()
        self.assertRedirects(response, conversation_url(conversation))
        self.assertIsNone(conversation.booking)
        self.assertEqual(conversation.owner, self.owner)

    def test_opening_it_again_reuses_the_conversation(self):
        self.client.force_login(self.owner)
        self.client.get(self.url(self.caregiver))
        self.client.get(self.url(self.caregiver))
        self.assertEqual(Conversation.objects.count(), 1)

    def test_caregiver_accounts_cannot_start_one(self):
        self.client.force_login(self.sitter)
        for caregiver in (self.caregiver, self.other_caregiver):
            response = self.client.get(self.url(caregiver))
            self.assertRedirects(
                response,
                reverse("caregiver", args=[caregiver.pk]),
                fetch_redirect_response=False,
            )
        self.assertFalse(Conversation.objects.exists())

    def test_profile_without_an_account_is_not_found(self):
        lonely = CaregiverProfile.objects.create(
            name="No Account", service_area="Bronx"
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url(lonely)).status_code, 404)

    def test_no_request_yet_card_for_the_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url(self.caregiver), follow=True)
        self.assertContains(response, "No request yet")
        self.assertContains(
            response, "Ask Chloe anything, then request care when you’re ready."
        )
        self.assertContains(
            response,
            f'href="{reverse("bookings:booking_create")}?caregiver={self.caregiver.pk}"',
        )
        self.assertContains(response, 'placeholder="Message Chloe…"')

    def test_no_request_button_when_caregiver_is_not_taking_bookings(self):
        self.caregiver.accepting_new_bookings = False
        self.caregiver.save()
        self.client.force_login(self.owner)
        response = self.client.get(self.url(self.caregiver), follow=True)
        self.assertContains(response, "No request yet")
        self.assertNotContains(response, ">Request care</a>")

    def test_caregiver_sees_the_owner_is_asking(self):
        conversation = self.general()
        self.say(conversation, self.owner, "Do you give pills to cats?")
        self.client.force_login(self.sitter)
        response = self.client.get(conversation_url(conversation))
        self.assertContains(
            response, "Kat is asking questions before sending a request."
        )
        self.assertContains(response, "Pet owner")
        self.assertNotContains(response, ">Request care</a>")

    def test_profile_page_has_a_message_button(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertContains(response, self.url(self.caregiver))
        self.assertContains(response, "Message Chloe")

    def test_no_message_button_for_caregiver_accounts(self):
        self.client.force_login(self.other_sitter)
        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertNotContains(response, self.url(self.caregiver))


class BookingConversationTests(MessagingTestData):
    """Messages and care updates about a booking."""

    def url(self, booking):
        return reverse("messaging:message_booking", args=[booking.pk])

    def test_owner_and_caregiver_share_one_conversation(self):
        booking = self.make_booking()
        self.client.force_login(self.owner)
        first = self.client.get(self.url(booking))
        self.client.force_login(self.sitter)
        second = self.client.get(self.url(booking))
        conversation = Conversation.objects.get()
        self.assertRedirects(first, conversation_url(conversation))
        self.assertRedirects(second, conversation_url(conversation))
        self.assertEqual(conversation.booking, booking)
        self.assertEqual(conversation.owner, self.owner)
        self.assertEqual(conversation.caregiver, self.caregiver)

    def test_others_cannot_open_it(self):
        booking = self.make_booking()
        for user in (self.other_owner, self.other_sitter):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url(booking)).status_code, 404)

    def test_booking_card_while_care_is_happening(self):
        booking = self.make_booking()
        self.client.force_login(self.owner)
        response = self.client.get(self.url(booking), follow=True)
        self.assertContains(response, "Miso · Drop-in visit")
        self.assertContains(response, "In progress")
        self.assertContains(response, f'href="{booking.get_absolute_url()}"')
        self.assertContains(response, "View booking")
        self.assertNotContains(response, "No request yet")

    def test_caregiver_sends_a_care_update(self):
        booking = self.make_booking()
        conversation = Conversation.objects.create(
            owner=self.owner, caregiver=self.caregiver, booking=booking
        )
        self.client.force_login(self.sitter)
        self.client.post(
            send_url(conversation), {"body": "Miso is hiding under the bed."}
        )
        self.client.force_login(self.owner)
        response = self.client.get(INBOX)
        self.assertContains(response, "Miso is hiding under the bed.")
        self.assertContains(response, '<span class="nav-badge">', count=0)

    def test_booking_page_links_to_its_messages(self):
        booking = self.make_booking(Status.PENDING, timedelta(days=2))
        self.client.force_login(self.owner)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, self.url(booking))
        self.assertContains(response, "Message Chloe")
        self.client.force_login(self.sitter)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Message Kat")


class SendMessageTests(MessagingTestData):
    def setUp(self):
        self.conversation = self.general()
        self.client.force_login(self.owner)

    def test_send(self):
        response = self.client.post(
            send_url(self.conversation), {"body": "  Do you take rabbits?  "}
        )
        self.assertRedirects(
            response,
            conversation_url(self.conversation) + "#latest",
            fetch_redirect_response=False,
        )
        message = Message.objects.get()
        self.assertEqual(message.body, "Do you take rabbits?")
        self.assertEqual(message.sender, self.owner)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.last_message_at, message.created_at)

    def test_empty_message_is_not_sent(self):
        response = self.client.post(
            send_url(self.conversation), {"body": "   "}, follow=True
        )
        self.assertContains(response, "Write a message before sending.")
        self.assertFalse(Message.objects.exists())

    def test_too_long_message_is_not_sent(self):
        body = "a" * (MAX_MESSAGE_LENGTH + 1)
        response = self.client.post(
            send_url(self.conversation), {"body": body}, follow=True
        )
        self.assertContains(response, "Messages can be up to 2,000 characters.")
        self.assertFalse(Message.objects.exists())

    def test_only_people_in_the_conversation_can_send(self):
        for user in (self.other_owner, self.other_sitter):
            self.client.force_login(user)
            response = self.client.post(send_url(self.conversation), {"body": "Hi"})
            self.assertEqual(response.status_code, 404)
        self.assertFalse(Message.objects.exists())

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(send_url(self.conversation)).status_code, 405)

    def test_caregiver_can_reply(self):
        self.client.force_login(self.sitter)
        self.client.post(send_url(self.conversation), {"body": "Yes!"})
        self.assertEqual(Message.objects.get().sender, self.sitter)


class MessageHistoryTests(MessagingTestData):
    """View Message History: the inbox and each conversation's full history."""

    def test_login_required(self):
        self.assertEqual(self.client.get(INBOX).status_code, 302)

    def test_empty_inbox_for_an_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(INBOX)
        self.assertContains(response, "No messages yet")
        self.assertContains(response, reverse("caregiver_list"))

    def test_empty_inbox_for_a_caregiver(self):
        self.client.force_login(self.sitter)
        response = self.client.get(INBOX)
        self.assertContains(response, "When pet owners message you")

    def test_conversations_without_messages_are_not_listed(self):
        self.general()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(INBOX).context["conversations"], [])

    def test_newest_conversation_first_and_open(self):
        now = timezone.now()
        older = self.general()
        self.say(older, self.owner, "Older chat", now - timedelta(days=2))
        newer = self.general(caregiver=self.other_caregiver)
        self.say(newer, self.other_sitter, "Newest reply", now)
        self.client.force_login(self.owner)
        response = self.client.get(INBOX)
        self.assertEqual(
            [c.pk for c in response.context["conversations"]], [newer.pk, older.pk]
        )
        self.assertEqual(response.context["selected"].pk, newer.pk)
        self.assertFalse(response.context["chosen"])

    def test_full_history_in_order_with_sides(self):
        conversation = self.general()
        now = timezone.now()
        self.say(conversation, self.owner, "Hi Chloe!", now - timedelta(minutes=3))
        self.say(conversation, self.sitter, "Hi Kat!", now - timedelta(minutes=2))
        self.say(
            conversation, self.owner, "Free next weekend?", now - timedelta(minutes=1)
        )
        self.client.force_login(self.owner)
        response = self.client.get(conversation_url(conversation))
        html = response.content.decode().split('id="chat-messages"')[1]
        self.assertLess(html.index("Hi Chloe!"), html.index("Hi Kat!"))
        self.assertLess(html.index("Hi Kat!"), html.index("Free next weekend?"))
        self.assertContains(response, 'class="bubble-row is-mine"', count=2)
        self.assertContains(response, 'class="bubble-row is-theirs"', count=1)
        self.assertContains(response, 'id="latest"', count=1)
        self.assertTrue(response.context["chosen"])

    def test_messages_keep_line_breaks_and_are_escaped(self):
        conversation = self.general()
        self.say(conversation, self.owner, "Line one\nLine <b>two</b>")
        self.client.force_login(self.owner)
        response = self.client.get(conversation_url(conversation))
        self.assertContains(response, "Line one<br>Line &lt;b&gt;two&lt;/b&gt;")

    def test_preview_and_unread_marker(self):
        conversation = self.general()
        self.say(conversation, self.sitter, "Totally fine! I'll use the harness.")
        other = self.general(caregiver=self.other_caregiver)
        self.say(other, self.owner, "Are you free next weekend?")
        self.client.force_login(self.owner)
        response = self.client.get(conversation_url(other))
        rows = {c.pk: c for c in response.context["conversations"]}
        self.assertTrue(rows[conversation.pk].unread)
        self.assertEqual(rows[other.pk].preview, "You: Are you free next weekend?")
        self.assertContains(response, "is-unread", count=1)

    def test_opening_a_conversation_marks_it_read(self):
        conversation = self.general()
        self.say(conversation, self.sitter, "Hi Kat!")
        self.client.force_login(self.owner)
        before = self.client.get(reverse("pets:list"))
        self.assertContains(before, '<span class="nav-badge">')
        self.client.get(conversation_url(conversation))
        after = self.client.get(reverse("pets:list"))
        self.assertNotContains(after, '<span class="nav-badge">')
        self.assertEqual(unread_count(self.owner), 0)

    def test_new_empty_conversation_is_shown_at_the_top(self):
        older = self.general(caregiver=self.other_caregiver)
        self.say(older, self.owner, "Hello Alicia")
        fresh = self.general()
        self.client.force_login(self.owner)
        response = self.client.get(conversation_url(fresh))
        self.assertEqual(response.context["conversations"][0].pk, fresh.pk)
        self.assertContains(response, "Say hi to Chloe")

    def test_others_cannot_see_a_conversation(self):
        conversation = self.general()
        for user in (self.other_owner, self.other_sitter):
            self.client.force_login(user)
            response = self.client.get(conversation_url(conversation))
            self.assertEqual(response.status_code, 404)

    def test_messages_tab_in_both_navs(self):
        for user in (self.owner, self.sitter):
            self.client.force_login(user)
            response = self.client.get(INBOX)
            self.assertContains(response, f'<a href="{INBOX}" class="active">Messages')


class LatestMessageTests(MessagingTestData):
    """The open conversation checks for new messages (care updates) to refresh."""

    def test_latest_message_id(self):
        conversation = self.general()
        url = reverse("messaging:latest", args=[conversation.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).json(), {"latest_id": 0})
        message = self.say(conversation, self.sitter, "Just got in!")
        self.assertEqual(self.client.get(url).json(), {"latest_id": message.pk})

    def test_others_cannot_check(self):
        conversation = self.general()
        self.client.force_login(self.other_owner)
        url = reverse("messaging:latest", args=[conversation.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
