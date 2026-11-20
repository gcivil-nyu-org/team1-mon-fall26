"""#103 Restrict Forum Posting, as in Kat's Figma: on the Users page, admins
stop an account posting in the forum without restricting the whole account,
and restore it later."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts import restriction
from accounts.restriction import restrict_forum

from .test_user_list import StaffTestData, detail_url

User = get_user_model()


def is_forum_restricted(user):
    """Looked up again, since the test's copy of the account is cached."""
    return restriction.is_forum_restricted(User.objects.get(pk=user.pk))


def restrict_url(user):
    return reverse("staff:restrict_forum", args=[user.pk])


def restore_url(user):
    return reverse("staff:restore_forum", args=[user.pk])


class RestrictForumTests(StaffTestData):
    def test_accounts_have_a_restrict_forum_button(self):
        response = self.client.get(detail_url(self.owner))
        self.assertContains(response, "confirm=forum")
        self.assertContains(response, "Restrict forum posting")
        self.assertNotContains(response, "Restore posting")

    def test_no_button_for_deleted_accounts(self):
        response = self.client.get(detail_url(self.gone))
        self.assertNotContains(response, "confirm=forum")

    def test_restrict_asks_for_confirmation_first(self):
        response = self.client.get(detail_url(self.owner) + "?confirm=forum")
        self.assertContains(response, "Restrict Kat from the forum?")
        self.assertContains(
            response,
            "Kat won’t be able to create posts or comments. "
            "The rest of PawPal still works as usual.",
        )
        self.assertContains(response, f'action="{restrict_url(self.owner)}"')
        self.assertFalse(is_forum_restricted(self.owner))

    def test_no_popup_when_already_restricted_or_not_allowed(self):
        restrict_forum(self.owner)
        for account in (self.owner, self.gone):
            response = self.client.get(detail_url(account) + "?confirm=forum")
            self.assertNotContains(response, "from the forum?</h2>")

    def test_restricting(self):
        response = self.client.post(restrict_url(self.owner), follow=True)
        self.assertRedirects(
            response, detail_url(self.owner) + "?done=forum_restricted"
        )
        self.assertContains(
            response,
            "Forum posting restricted. Kat can still use the rest of PawPal.",
        )
        self.assertTrue(is_forum_restricted(self.owner))
        self.assertContains(response, "Forum restricted</span>")
        self.assertContains(response, "Can’t post in the forum since Today")
        self.assertContains(
            response,
            "Kat can’t create posts or comments. The rest of PawPal works as usual.",
        )
        self.assertContains(response, "Restore posting")
        self.assertContains(response, f'action="{restore_url(self.owner)}"')
        self.assertNotContains(response, "Restrict forum posting")
        # Only the forum: the account itself isn't restricted (#92).
        self.owner.account_profile.refresh_from_db()
        self.assertIsNone(self.owner.account_profile.restricted_at)
        self.assertContains(response, "Restrict account")

    def test_restricting_twice_keeps_the_first_time(self):
        restrict_forum(self.owner)
        profile = self.owner.account_profile
        profile.refresh_from_db()
        when = profile.forum_restricted_at
        self.client.post(restrict_url(self.owner))
        profile.refresh_from_db()
        self.assertEqual(profile.forum_restricted_at, when)

    def test_restoring(self):
        restrict_forum(self.owner)
        response = self.client.post(restore_url(self.owner), follow=True)
        self.assertRedirects(response, detail_url(self.owner) + "?done=forum_restored")
        self.assertContains(
            response, "Forum posting restored. Kat can post and comment again."
        )
        self.assertFalse(is_forum_restricted(self.owner))
        self.assertContains(response, "Restrict forum posting")

    def test_restricted_tab_lists_it(self):
        restrict_forum(self.owner)
        response = self.client.get(reverse("staff:user_list") + "?tab=restricted")
        self.assertContains(response, "Kat W")
        self.assertNotContains(response, "Chloe Shih")

    def test_reinstating_an_account_keeps_the_forum_restriction(self):
        restriction.restrict(self.owner, "Spam")
        restrict_forum(self.owner)
        response = self.client.post(
            reverse("staff:reinstate_user", args=[self.owner.pk]), follow=True
        )
        self.assertContains(response, "Account reinstated.")
        self.assertContains(response, "Forum restricted</span>")

    def test_banner_only_while_in_that_state(self):
        response = self.client.get(detail_url(self.owner) + "?done=forum_restricted")
        self.assertNotContains(response, "Forum posting restricted.")
        restrict_forum(self.owner)
        response = self.client.get(detail_url(self.owner) + "?done=forum_restored")
        self.assertNotContains(response, "Forum posting restored.")

    def test_only_admins_can_restrict_or_restore(self):
        self.client.force_login(self.sitter)
        self.assertEqual(self.client.post(restrict_url(self.owner)).status_code, 403)
        self.assertFalse(is_forum_restricted(self.owner))
        restrict_forum(self.owner)
        self.assertEqual(self.client.post(restore_url(self.owner)).status_code, 403)
        self.assertTrue(is_forum_restricted(self.owner))

    def test_cant_restrict_admins_yourself_or_deleted_accounts(self):
        other_admin = User.objects.create_user("bo", is_staff=True)
        for account in (other_admin, self.admin, self.gone):
            self.assertIn(
                self.client.post(restrict_url(account)).status_code, (403, 404)
            )
            self.assertFalse(is_forum_restricted(account))

    def test_needs_a_post(self):
        self.assertEqual(self.client.get(restrict_url(self.owner)).status_code, 405)
        self.assertEqual(self.client.get(restore_url(self.owner)).status_code, 405)

    def test_account_without_a_profile(self):
        # Older accounts may not have an AccountProfile yet.
        old = User.objects.create_user("old", first_name="Olga")
        self.assertFalse(is_forum_restricted(old))
        self.client.post(restrict_url(old))
        old.refresh_from_db()
        self.assertTrue(is_forum_restricted(old))
