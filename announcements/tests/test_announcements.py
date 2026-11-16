"""Post Platform Announcements: admins create, save, publish, update and remove
announcements; pet owners and caregivers see the ones meant for them."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from announcements.models import Announcement, AnnouncementDismissal, is_caregiver
from announcements.templatetags.announcement_tags import day
from caregivers.models import CaregiverProfile

User = get_user_model()
MANAGE = reverse("announcements:manage")
CREATE = reverse("announcements:create")


def detail_url(a):
    return reverse("announcements:detail", args=[a.pk])


class AnnouncementData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "admin", password="pw-12345!", is_staff=True
        )
        cls.owner = User.objects.create_user("kat", password="pw-12345!")
        AccountProfile.objects.create(user=cls.owner, role="pet_owner")
        cls.sitter = User.objects.create_user("chloe", password="pw-12345!")
        AccountProfile.objects.create(user=cls.sitter, role="caregiver")
        # Signed up as a caregiver but no caregiver profile yet.
        cls.new_sitter = User.objects.create_user("sam", password="pw-12345!")
        AccountProfile.objects.create(user=cls.new_sitter, role="caregiver")
        CaregiverProfile.objects.create(
            user=cls.sitter, name="Chloe Shih", service_area="Park Slope"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def make(self, title="Scheduled maintenance Sunday", status="published", **extra):
        fields = {
            "kind": "maintenance",
            "audience": "everyone",
            "message": "PawPal will be down Sun 2-4 AM.",
            "created_by": self.admin,
        }
        fields.update(extra)
        if status == "published":
            fields.setdefault("published_at", timezone.now())
        return Announcement.objects.create(title=title, status=status, **fields)

    def post_form(self, url, action, **data):
        fields = {
            "title": "Messages are back to normal",
            "kind": "update",
            "audience": "everyone",
            "message": "Some messages were delayed this morning.",
            "action": action,
        }
        fields.update(data)
        return self.client.post(url, fields)


class AdminOnlyTests(AnnouncementData):
    def test_admins_only(self):
        a = self.make()
        urls = [
            MANAGE,
            CREATE,
            detail_url(a),
            reverse("announcements:edit", args=[a.pk]),
        ]
        self.client.force_login(self.owner)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        for name in ("publish", "remove"):
            url = reverse(f"announcements:{name}", args=[a.pk])
            self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(MANAGE).status_code, 302)

    def test_admin_nav_link(self):
        response = self.client.get(MANAGE)
        self.assertContains(response, 'class="active">Announcements</a>')


class ListTests(AnnouncementData):
    def test_published_tab_newest_first_with_the_newest_open(self):
        old = self.make(
            "Updated cancellation policy", kind="policy", audience="pet_owners"
        )
        Announcement.objects.filter(pk=old.pk).update(
            published_at=timezone.now() - timedelta(days=9)
        )
        new = self.make()
        self.make("Holiday hours", status="draft")
        response = self.client.get(MANAGE)
        self.assertEqual(
            [a.pk for a in response.context["announcements"]], [new.pk, old.pk]
        )
        self.assertEqual(response.context["selected"], new)
        tabs = {t["key"]: t["count"] for t in response.context["tabs"]}
        self.assertEqual(tabs, {"published": 2, "drafts": 1})
        self.assertContains(response, "Pet owners · ")
        self.assertContains(response, "What users see")
        self.assertContains(response, "Posted")

    def test_drafts_tab(self):
        draft = self.make("Holiday hours", status="draft")
        response = self.client.get(MANAGE, {"tab": "drafts"})
        self.assertEqual(response.context["selected"], draft)
        self.assertContains(response, "Last saved")
        self.assertContains(response, "Delete draft")
        self.assertContains(response, reverse("announcements:publish", args=[draft.pk]))

    def test_unknown_tab_and_empty_state(self):
        response = self.client.get(MANAGE, {"tab": "trash"})
        self.assertEqual(response.context["tab"], "published")
        self.assertContains(response, "No published announcements.")
        self.assertContains(response, "Nothing here yet")

    def test_detail(self):
        a = self.make()
        response = self.client.get(detail_url(a))
        self.assertEqual(response.context["selected"], a)
        self.assertContains(response, "Scheduled maintenance Sunday")


class CreateTests(AnnouncementData):
    def test_form(self):
        response = self.client.get(CREATE)
        self.assertContains(response, "New announcement")
        self.assertContains(response, 'value="publish"')
        self.assertContains(response, 'value="draft"')

    def test_publish(self):
        response = self.post_form(CREATE, "publish")
        a = Announcement.objects.get()
        self.assertRedirects(
            response, detail_url(a) + "?done=published", fetch_redirect_response=False
        )
        self.assertTrue(a.is_published)
        self.assertIsNotNone(a.published_at)
        self.assertEqual(a.created_by, self.admin)
        page = self.client.get(detail_url(a) + "?done=published")
        self.assertContains(
            page, "Published. Users will see the announcement on their home page."
        )

    def test_save_draft(self):
        response = self.post_form(CREATE, "draft")
        a = Announcement.objects.get()
        self.assertRedirects(
            response, detail_url(a) + "?done=drafted", fetch_redirect_response=False
        )
        self.assertEqual(a.status, Announcement.Status.DRAFT)
        self.assertIsNone(a.published_at)

    def test_publishing_needs_every_field(self):
        response = self.client.post(CREATE, {"title": "  ", "action": "publish"})
        self.assertContains(response, "Almost there.")
        for error in (
            "Add a title.",
            "Pick a type.",
            "Pick who sees it.",
            "Add a message.",
        ):
            self.assertContains(response, error)
        self.assertFalse(Announcement.objects.exists())

    def test_a_draft_only_needs_a_title(self):
        self.client.post(CREATE, {"title": "Holiday hours", "action": "draft"})
        a = Announcement.objects.get()
        self.assertEqual((a.kind, a.audience, a.message), ("", "", ""))
        response = self.client.post(CREATE, {"title": "", "action": "draft"})
        self.assertContains(response, "Add a title.")
        self.assertNotContains(response, "Pick a type.")

    def test_unknown_values_are_rejected(self):
        response = self.post_form(CREATE, "publish", kind="party", audience="admins")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Announcement.objects.exists())


class EditTests(AnnouncementData):
    def test_form_is_filled_in(self):
        a = self.make()
        response = self.client.get(reverse("announcements:edit", args=[a.pk]))
        self.assertContains(response, "Edit announcement")
        self.assertContains(response, 'value="Scheduled maintenance Sunday"')
        self.assertContains(response, 'value="maintenance" checked')
        self.assertContains(response, "Save changes")
        self.assertNotContains(response, "Save draft")

    def test_update_a_published_announcement(self):
        a = self.make()
        published = a.published_at
        url = reverse("announcements:edit", args=[a.pk])
        response = self.post_form(url, "save", title="Maintenance moved to Monday")
        self.assertRedirects(
            response, detail_url(a) + "?done=saved", fetch_redirect_response=False
        )
        a.refresh_from_db()
        self.assertEqual(a.title, "Maintenance moved to Monday")
        self.assertTrue(a.is_published)
        self.assertEqual(a.published_at, published)
        page = self.client.get(detail_url(a) + "?done=saved")
        self.assertContains(page, "Changes saved.")

    def test_a_published_announcement_keeps_every_field(self):
        a = self.make()
        url = reverse("announcements:edit", args=[a.pk])
        response = self.post_form(url, "save", message="")
        self.assertContains(response, "Add a message.")
        a.refresh_from_db()
        self.assertTrue(a.message)

    def test_edit_and_publish_a_draft(self):
        draft = self.make(
            "Holiday hours", status="draft", kind="", audience="", message=""
        )
        url = reverse("announcements:edit", args=[draft.pk])
        self.post_form(url, "draft", title="Holiday hours", message="")
        draft.refresh_from_db()
        self.assertEqual(draft.status, Announcement.Status.DRAFT)
        response = self.post_form(url, "publish", title="Holiday hours")
        self.assertRedirects(
            response,
            detail_url(draft) + "?done=published",
            fetch_redirect_response=False,
        )
        draft.refresh_from_db()
        self.assertTrue(draft.is_published)


class PublishAndRemoveTests(AnnouncementData):
    def test_publish_a_draft(self):
        draft = self.make("Holiday hours", status="draft")
        response = self.client.post(reverse("announcements:publish", args=[draft.pk]))
        self.assertRedirects(
            response,
            detail_url(draft) + "?done=published",
            fetch_redirect_response=False,
        )
        draft.refresh_from_db()
        self.assertTrue(draft.is_published)

    def test_publishing_twice_changes_nothing(self):
        a = self.make()
        posted = a.published_at
        self.client.post(reverse("announcements:publish", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.published_at, posted)

    def test_an_unfinished_draft_opens_the_form_with_errors(self):
        draft = self.make("Holiday hours", status="draft", kind="", message="")
        response = self.client.post(reverse("announcements:publish", args=[draft.pk]))
        self.assertContains(response, "Pick a type.")
        self.assertContains(response, "Add a message.")
        draft.refresh_from_db()
        self.assertEqual(draft.status, Announcement.Status.DRAFT)

    def test_remove_asks_first(self):
        a = self.make()
        response = self.client.get(detail_url(a), {"confirm": "remove"})
        self.assertContains(response, "Remove this announcement?")
        self.assertContains(response, "Users won't see it anymore.")

    def test_remove(self):
        a = self.make()
        response = self.client.post(reverse("announcements:remove", args=[a.pk]))
        self.assertRedirects(
            response,
            MANAGE + "?tab=published&done=removed",
            fetch_redirect_response=False,
        )
        self.assertFalse(Announcement.objects.exists())
        page = self.client.get(MANAGE + "?tab=published&done=removed")
        self.assertContains(page, "Announcement removed.")

    def test_delete_a_draft(self):
        draft = self.make("Holiday hours", status="draft")
        page = self.client.get(detail_url(draft), {"confirm": "remove"})
        self.assertContains(page, "Delete this draft?")
        response = self.client.post(reverse("announcements:remove", args=[draft.pk]))
        self.assertRedirects(
            response, MANAGE + "?tab=drafts&done=deleted", fetch_redirect_response=False
        )
        self.assertFalse(Announcement.objects.exists())

    def test_remove_needs_post(self):
        a = self.make()
        response = self.client.get(reverse("announcements:remove", args=[a.pk]))
        self.assertEqual(response.status_code, 405)


class WhatUsersSeeTests(AnnouncementData):
    """Published announcements are visible to the right people."""

    def banner(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("pets:list")).context.get("current_announcement")

    def test_everyone_sees_announcements_for_everyone(self):
        a = self.make()
        for user in (self.owner, self.sitter, self.new_sitter):
            self.assertEqual(self.banner(user), a)

    def test_audiences(self):
        owners = self.make("Cancellation policy", audience="pet_owners")
        sitters = self.make("Holiday availability", audience="caregivers")
        Announcement.objects.filter(pk=owners.pk).update(
            published_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(self.banner(self.owner), owners)
        self.assertEqual(self.banner(self.sitter), sitters)
        self.assertEqual(self.banner(self.new_sitter), sitters)

    def test_drafts_are_never_shown(self):
        self.make("Holiday hours", status="draft")
        self.assertFalse(self.banner(self.owner))

    def test_admins_and_visitors_get_no_banner(self):
        self.make()
        response = self.client.get(MANAGE)
        self.assertNotIn("current_announcement", response.context)
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "announcement-banner")

    def test_banner_on_the_page(self):
        self.make()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("pets:list"))
        self.assertContains(response, 'class="announcement-banner kind-maintenance"')
        self.assertContains(response, "PawPal will be down Sun 2-4 AM.")
        self.assertContains(response, "Close this announcement")

    def test_closing_the_banner(self):
        newest = self.make()
        older = self.make("New: Community forum", kind="update")
        Announcement.objects.filter(pk=older.pk).update(
            published_at=timezone.now() - timedelta(days=1)
        )
        self.client.force_login(self.owner)
        url = reverse("announcements:dismiss", args=[newest.pk])
        response = self.client.post(url, {"next": "/pets/"})
        self.assertRedirects(response, "/pets/", fetch_redirect_response=False)
        self.assertTrue(
            AnnouncementDismissal.objects.filter(
                announcement=newest, user=self.owner
            ).exists()
        )
        # The next one shows; closing twice is fine.
        self.assertEqual(self.banner(self.owner), older)
        self.client.post(url)
        self.assertEqual(AnnouncementDismissal.objects.count(), 1)
        # Other people still see it.
        self.assertEqual(self.banner(self.sitter), newest)

    def test_closing_stays_on_pawpal(self):
        a = self.make()
        self.client.force_login(self.owner)
        url = reverse("announcements:dismiss", args=[a.pk])
        response = self.client.post(url, {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_only_published_announcements_can_be_closed(self):
        draft = self.make("Holiday hours", status="draft")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("announcements:dismiss", args=[draft.pk]))
        self.assertEqual(response.status_code, 404)

    def test_removed_announcements_disappear(self):
        a = self.make()
        self.client.post(reverse("announcements:remove", args=[a.pk]))
        self.assertFalse(self.banner(self.owner))


class HelperTests(AnnouncementData):
    def test_is_caregiver(self):
        self.assertFalse(is_caregiver(self.owner))
        self.assertTrue(is_caregiver(self.sitter))
        self.assertTrue(is_caregiver(self.new_sitter))
        self.assertFalse(is_caregiver(self.admin))  # no profile at all

    def test_str(self):
        self.assertEqual(str(self.make()), "Scheduled maintenance Sunday")

    def test_day(self):
        now = timezone.now()
        self.assertEqual(day(None), "")
        self.assertEqual(day(now), "Today")
        with mock.patch(
            "django.utils.timezone.now",
            return_value=now.replace(month=6, day=15, hour=12),
        ):
            self.assertRegex(day(timezone.now() - timedelta(days=10)), r"^Jun \d{1,2}$")
            self.assertRegex(
                day(timezone.now() - timedelta(days=400)),
                r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$",
            )
