"""#92 Restrict or Reinstate User Account."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import AccountProfile

from accounts.restriction import RESTRICTED_MESSAGE, is_restricted, restrict
from caregivers.search import searchable_caregivers

from .test_user_list import LIST_URL, StaffTestData, detail_url

LOGIN_URL = reverse("login")


def restrict_url(user):
    return reverse("staff:restrict_user", args=[user.pk])


def reinstate_url(user):
    return reverse("staff:reinstate_user", args=[user.pk])


class RestrictTests(StaffTestData):
    def log_in(self, user):
        self.client.logout()
        return self.client.post(
            LOGIN_URL, {"username": user.username, "password": "pw-12345!"}
        )

    def test_admin_can_restrict_with_a_reason(self):
        response = self.client.get(detail_url(self.owner))
        self.assertContains(
            response,
            f'href="{detail_url(self.owner)}?confirm=restrict">Restrict account',
        )
        self.assertNotContains(response, f'action="{restrict_url(self.owner)}"')

        # The button opens a confirm popup with the reason box.
        response = self.client.get(detail_url(self.owner), {"confirm": "restrict"})
        self.assertContains(response, "Restrict Kat’s account?")
        self.assertContains(response, f'action="{restrict_url(self.owner)}"')
        self.assertContains(response, 'name="reason"')
        self.assertContains(response, f'href="{detail_url(self.owner)}">Cancel</a>')

        response = self.client.post(
            restrict_url(self.owner), {"reason": "Spam messages"}, follow=True
        )
        self.assertRedirects(response, detail_url(self.owner))
        self.assertContains(response, "Kat W&#x27;s account is restricted.")
        self.assertContains(response, "Spam messages")
        self.assertContains(response, "Reinstate account")
        self.owner.account_profile.refresh_from_db()
        self.assertIsNotNone(self.owner.account_profile.restricted_at)
        self.assertEqual(self.owner.account_profile.restriction_reason, "Spam messages")

    def test_restricted_is_shown_in_the_list(self):
        restrict(self.owner)
        response = self.client.get(LIST_URL)
        self.assertContains(response, "account-status-restricted")
        self.assertContains(response, "Restricted")

    def test_restricted_user_cannot_log_in(self):
        restrict(self.owner)
        response = self.log_in(self.owner)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This account is restricted.")
        self.assertNotContains(response, "Incorrect username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_on_a_restricted_account_says_incorrect(self):
        restrict(self.owner)
        self.client.logout()
        response = self.client.post(
            LOGIN_URL, {"username": "kat", "password": "wrong-password"}
        )
        self.assertContains(response, "Incorrect username or password.")

    def test_open_sessions_are_logged_out(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("pets:list")).status_code, 200)
        restrict(self.owner)
        response = self.client.get(reverse("pets:list"), follow=True)
        self.assertRedirects(response, LOGIN_URL)
        self.assertContains(response, RESTRICTED_MESSAGE.split(".")[0])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_restricted_caregiver_is_hidden_from_search(self):
        caregiver = self.sitter.caregiver_profile
        self.assertIn(caregiver, searchable_caregivers(self.owner))
        restrict(self.sitter)
        self.assertNotIn(caregiver, searchable_caregivers(self.owner))

    def test_admin_can_reinstate(self):
        restrict(self.owner, "Spam")
        response = self.client.post(reinstate_url(self.owner), follow=True)
        self.assertContains(response, "Kat W&#x27;s account is reinstated.")
        self.assertContains(response, "Restrict account")
        self.owner.account_profile.refresh_from_db()
        self.assertIsNone(self.owner.account_profile.restricted_at)
        self.assertEqual(self.owner.account_profile.restriction_reason, "")
        self.assertEqual(self.log_in(self.owner).status_code, 302)

    def test_repeating_an_action_changes_nothing(self):
        restrict(self.owner, "First")
        first = AccountProfile.objects.get(user=self.owner)
        self.client.post(restrict_url(self.owner), {"reason": "Second"})
        again = AccountProfile.objects.get(pk=first.pk)
        self.assertEqual(again.restricted_at, first.restricted_at)
        self.assertEqual(again.restriction_reason, "First")
        self.client.post(reinstate_url(self.sitter))
        self.assertFalse(is_restricted(self.sitter))

    def test_account_without_a_profile_gets_one(self):
        plain = get_user_model().objects.create_user("plain", password="pw-12345!")
        self.client.post(restrict_url(plain))
        plain.refresh_from_db()
        self.assertTrue(is_restricted(plain))

    def test_admins_themselves_and_deleted_accounts_cannot_be_restricted(self):
        other_admin = self.make("boss", "Bo", "S", "bo@example.com")
        other_admin.is_staff = True
        other_admin.save()
        for account in (self.admin, other_admin, self.gone):
            response = self.client.get(detail_url(account))
            self.assertNotContains(response, "Restrict account")
            self.assertEqual(self.client.post(restrict_url(account)).status_code, 403)
            self.assertEqual(self.client.post(reinstate_url(account)).status_code, 403)
        self.assertFalse(is_restricted(other_admin))

    def test_only_admins_and_only_post(self):
        self.assertEqual(self.client.get(restrict_url(self.owner)).status_code, 405)
        self.client.force_login(self.sitter)
        self.assertEqual(self.client.post(restrict_url(self.owner)).status_code, 403)
        self.assertFalse(is_restricted(self.owner))


class RestrictedTabTests(StaffTestData):
    def test_tabs_count_all_and_restricted_accounts(self):
        restrict(self.owner)
        restrict(self.gone)  # deleted accounts don't count as restricted
        response = self.client.get(LIST_URL)
        tabs = {t["key"]: t["count"] for t in response.context["tabs"]}
        self.assertEqual(tabs, {"all": 5, "restricted": 1})
        self.assertContains(response, f'href="{LIST_URL}?tab=restricted"')

    def test_restricted_tab_lists_only_restricted_accounts(self):
        restrict(self.owner)
        response = self.client.get(LIST_URL, {"tab": "restricted"})
        self.assertEqual(list(response.context["page"]), [self.owner])
        self.assertContains(response, f'href="{detail_url(self.owner)}?tab=restricted"')
        self.assertContains(response, 'name="tab" value="restricted"')

    def test_search_within_the_restricted_tab(self):
        restrict(self.owner)
        restrict(self.sitter)
        response = self.client.get(LIST_URL, {"tab": "restricted", "q": "chloe"})
        self.assertEqual(list(response.context["page"]), [self.sitter])
        self.assertContains(
            response, f'href="{detail_url(self.sitter)}?q=chloe&amp;tab=restricted"'
        )

    def test_empty_restricted_tab(self):
        response = self.client.get(LIST_URL, {"tab": "restricted"})
        self.assertContains(response, "No restricted accounts")
        self.assertIsNone(response.context["selected"])

    def test_no_popup_for_accounts_that_cant_be_restricted(self):
        restrict(self.owner)
        for account in (self.owner, self.admin, self.gone):
            response = self.client.get(detail_url(account), {"confirm": "restrict"})
            self.assertFalse(response.context["confirm"])
            self.assertNotContains(response, "modal-backdrop")
