"""#89 View User Accounts: admins see every pet owner and caregiver account,
with its type and status, and can open one for more details."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from staff.accounts import account_status, account_type

User = get_user_model()
LIST_URL = reverse("staff:user_list")


def detail_url(user):
    return reverse("staff:user_detail", args=[user.pk])


class StaffTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "admin", password="pw-12345!", is_staff=True, first_name="Ada"
        )
        cls.owner = cls.make("kat", "Kat", "W", "kat@example.com")
        cls.sitter = cls.make(
            "chloe", "Chloe", "Shih", "chloe@example.com", "caregiver"
        )
        CaregiverProfile.objects.create(
            user=cls.sitter, name="Chloe Shih", service_area="Park Slope"
        )
        cls.new = cls.make("sam", "Sam", "Lee", "sam@example.com", verified=False)
        cls.gone = cls.make("gone", "", "", "", active=False)

    @classmethod
    def make(cls, username, first, last, email, role="pet_owner", **flags):
        user = User.objects.create_user(
            username,
            email=email,
            password="pw-12345!",
            first_name=first,
            last_name=last,
            is_active=flags.get("active", True),
        )
        AccountProfile.objects.create(
            user=user, role=role, email_verified=flags.get("verified", True)
        )
        return user

    def setUp(self):
        self.client.force_login(self.admin)


class AccessTests(StaffTestData):
    def test_logged_out_visitors_go_to_log_in(self):
        self.client.logout()
        for url in (LIST_URL, detail_url(self.owner)):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_pet_owners_and_caregivers_are_refused(self):
        for user in (self.owner, self.sitter):
            self.client.force_login(user)
            self.assertEqual(self.client.get(LIST_URL).status_code, 403)
            self.assertEqual(self.client.get(detail_url(self.owner)).status_code, 403)

    def test_admins_start_on_users_and_see_it_in_the_menu(self):
        response = self.client.get(reverse("home"), follow=True)
        self.assertRedirects(response, LIST_URL)
        self.assertContains(response, f'href="{LIST_URL}" class="active">Users</a>')
        self.assertContains(response, '<span class="account-role">Admin</span>')
        self.assertNotContains(response, "Your neighborhood")

    def test_other_people_dont_see_the_users_link(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("pets:list"))
        self.assertNotContains(response, LIST_URL)


class ListTests(StaffTestData):
    def test_lists_every_account_with_type_and_status(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["page"].paginator.count, 5)
        for text in (
            "Kat W",
            "Chloe Shih",
            "Caregiver",
            "Pet owner",
            "Admin",
            "Email not confirmed",
            "Deleted",
            "Active",
        ):
            self.assertContains(response, text)

    def test_first_account_is_shown_next_to_the_list(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["selected"], self.gone)
        self.assertContains(response, 'class="staff-row is-selected"')
        self.assertContains(response, 'id="account-name">gone</h2>')

    def test_opening_an_account_keeps_the_list(self):
        response = self.client.get(detail_url(self.owner))
        self.assertEqual(response.context["selected"], self.owner)
        self.assertEqual(len(response.context["page"]), 5)
        self.assertContains(response, 'aria-current="true"', count=1)

    def test_newest_first_and_each_row_opens_the_account(self):
        response = self.client.get(LIST_URL)
        accounts = list(response.context["page"])
        self.assertEqual(accounts[0], self.gone)
        self.assertEqual(accounts[-1], self.admin)
        for user in accounts:
            self.assertContains(response, f'href="{detail_url(user)}"')

    def test_pages_of_25(self):
        for i in range(25):
            User.objects.create_user(f"user{i:02}")
        first = self.client.get(LIST_URL)
        self.assertEqual(len(first.context["page"]), 25)
        self.assertContains(first, "Page 1 of 2")
        self.assertContains(first, f'href="{LIST_URL}?page=2"')
        second = self.client.get(LIST_URL, {"page": 2})
        self.assertEqual(len(second.context["page"]), 5)
        self.assertContains(second, f'href="{LIST_URL}?page=1"')

    def test_type_and_status_rules(self):
        self.assertEqual(account_type(self.admin), "Admin")
        self.assertEqual(account_type(self.sitter), "Caregiver")
        self.assertEqual(account_type(self.owner), "Pet owner")
        no_profile = User.objects.create_user("plain")
        self.assertEqual(account_type(no_profile), "Pet owner")
        self.assertEqual(account_status(no_profile), ("active", "Active"))
        self.assertEqual(
            account_status(self.new), ("unverified", "Email not confirmed")
        )
        self.assertEqual(account_status(self.gone), ("deleted", "Deleted"))


class DetailTests(StaffTestData):
    def test_shows_the_accounts_details(self):
        response = self.client.get(detail_url(self.owner))
        for text in (
            "Kat W",
            "@kat",
            "kat@example.com",
            "Pet owner",
            "Active",
            "Joined",
            "Never",
        ):
            self.assertContains(response, text)

    def test_deleted_account_has_no_email(self):
        response = self.client.get(detail_url(self.gone))
        self.assertContains(response, "@gone")
        self.assertContains(response, "Deleted")
        self.assertContains(response, "<dd>—</dd>", html=True)

    def test_unknown_account_is_404(self):
        self.assertEqual(self.client.get("/manage/users/9999/").status_code, 404)
