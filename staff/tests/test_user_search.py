"""#90 Search User Accounts: admins find an account by name, username or email."""

from django.urls import reverse

from .test_user_list import LIST_URL, StaffTestData, detail_url


class SearchTests(StaffTestData):
    def found(self, query):
        response = self.client.get(LIST_URL, {"q": query})
        return response, list(response.context["page"])

    def test_by_name_username_or_email(self):
        cases = {
            "Chloe": [self.sitter],
            "shih": [self.sitter],
            "Kat W": [self.owner],
            "chloe shih": [self.sitter],
            "@example.com": [self.new, self.sitter, self.owner],
            "SAM": [self.new],
            "gone": [self.gone],
        }
        for query, accounts in cases.items():
            self.assertEqual(self.found(query)[1], accounts, query)

    def test_results_say_how_many_and_open_the_account(self):
        response, _ = self.found("kat")
        self.assertContains(response, "1 account matching “kat”")
        self.assertContains(response, f'href="{detail_url(self.owner)}"')
        self.assertContains(response, 'value="kat"')
        self.assertContains(response, f'href="{LIST_URL}">Clear</a>')

    def test_message_when_nothing_matches(self):
        response, accounts = self.found("nobody")
        self.assertEqual(accounts, [])
        self.assertContains(response, "No accounts match “nobody”")
        self.assertContains(response, "Show all users")

    def test_blank_search_lists_everyone(self):
        response, accounts = self.found("   ")
        self.assertEqual(len(accounts), 5)
        self.assertContains(response, "5 accounts on PawPal")
        self.assertNotContains(response, ">Clear</a>")

    def test_pages_keep_the_search(self):
        for i in range(30):
            self.make(f"walker{i:02}", "Walker", f"{i}", f"w{i}@example.com")
        response, accounts = self.found("walker")
        self.assertEqual(len(accounts), 25)
        self.assertContains(response, 'href="?q=walker&amp;page=2"')
        second = self.client.get(LIST_URL, {"q": "walker", "page": 2})
        self.assertEqual(len(second.context["page"]), 5)

    def test_search_box_is_on_the_users_page(self):
        response = self.client.get(reverse("staff:user_list"))
        self.assertContains(response, 'role="search"')
        self.assertContains(response, 'placeholder="Search name, username or email"')
