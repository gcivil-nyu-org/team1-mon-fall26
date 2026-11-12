"""#68 Browse Forum Posts: pet owners and caregivers see the newest posts
first, each with its title and basic information, and can open a post to
read all of it."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from forum.authors import initials, role, short_name
from forum.models import Post
from forum.views import PER_PAGE

User = get_user_model()
LIST_URL = reverse("forum:list")


def detail_url(post):
    return reverse("forum:detail", args=[post.pk])


class ForumTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "kat", password="pw-12345!", first_name="Kat", last_name="Wong"
        )
        AccountProfile.objects.create(user=cls.owner)
        cls.sitter = User.objects.create_user(
            "chloe", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        AccountProfile.objects.create(
            user=cls.sitter, role=AccountProfile.Role.CAREGIVER
        )
        CaregiverProfile.objects.create(
            user=cls.sitter, name="Chloe Shih", service_area="Park Slope"
        )
        cls.older = cls.post(cls.sitter, "Quiet dog runs?", "Any in Park Slope?", 2)
        cls.newer = cls.post(
            cls.owner,
            "Best cafes for dogs",
            "Lucky Dog has water bowls.\n\nThey also sell treats.",
            1,
        )

    @classmethod
    def post(cls, author, title, body, days_ago=0):
        post = Post.objects.create(author=author, title=title, body=body)
        Post.objects.filter(pk=post.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        post.refresh_from_db()
        return post

    def setUp(self):
        self.client.force_login(self.owner)


class AccessTests(ForumTestData):
    def test_log_in_first(self):
        self.client.logout()
        for url in (LIST_URL, detail_url(self.newer)):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_owners_and_caregivers_see_forum_in_the_menu(self):
        for user, page in (
            (self.owner, reverse("pets:list")),
            (self.sitter, reverse("messaging:inbox")),
        ):
            self.client.force_login(user)
            response = self.client.get(page)
            self.assertContains(response, f'href="{LIST_URL}" class="">Forum</a>')

    def test_forum_is_active_in_the_menu_on_forum_pages(self):
        for url in (LIST_URL, detail_url(self.newer)):
            response = self.client.get(url)
            self.assertContains(response, f'href="{LIST_URL}" class="active">Forum</a>')


class ListTests(ForumTestData):
    def test_newest_posts_first_with_basic_information(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(list(response.context["page"]), [self.newer, self.older])
        for text in (
            "Best cafes for dogs",
            "Lucky Dog has water bowls.",
            "Kat W.",
            "Pet owner",
            "Quiet dog runs?",
            "Chloe S.",
            "Caregiver",
            self.newer.created_at.strftime("%b %-d, %Y"),
        ):
            self.assertContains(response, text)

    def test_each_post_opens_its_page(self):
        response = self.client.get(LIST_URL)
        for post in (self.newer, self.older):
            self.assertContains(response, f'href="{detail_url(post)}"')

    def test_long_posts_are_cut_short_in_the_list(self):
        self.post(self.owner, "Long one", "word " * 100)
        response = self.client.get(LIST_URL)
        self.assertContains(response, "…")
        self.assertNotContains(response, "word " * 100)

    def test_pages_of_posts(self):
        for i in range(PER_PAGE):
            self.post(self.owner, f"Post {i}", "Hello")
        first = self.client.get(LIST_URL)
        self.assertEqual(len(first.context["page"]), PER_PAGE)
        self.assertContains(first, "Page 1 of 2")
        self.assertContains(first, 'href="?page=2">Older posts')
        second = self.client.get(LIST_URL, {"page": 2})
        self.assertEqual(list(second.context["page"]), [self.newer, self.older])
        self.assertContains(second, 'href="?page=1">Newer posts')

    def test_no_posts_yet(self):
        Post.objects.all().delete()
        response = self.client.get(LIST_URL)
        self.assertContains(response, "No posts yet")
        self.assertNotContains(response, "Page 1")


class DetailTests(ForumTestData):
    def test_shows_the_whole_post(self):
        response = self.client.get(detail_url(self.newer))
        self.assertContains(response, "<h1>Best cafes for dogs</h1>", html=True)
        self.assertContains(response, "<p>Lucky Dog has water bowls.</p>", html=True)
        self.assertContains(response, "<p>They also sell treats.</p>", html=True)
        self.assertContains(response, "Kat W.")
        self.assertContains(response, "Back to forum")
        self.assertContains(response, f'href="{LIST_URL}"')

    def test_text_is_escaped(self):
        post = self.post(self.owner, "<b>Hi</b>", "<script>alert(1)</script>")
        response = self.client.get(detail_url(post))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;b&gt;Hi&lt;/b&gt;")

    def test_unknown_post_is_404(self):
        response = self.client.get(reverse("forum:detail", args=[9999]))
        self.assertEqual(response.status_code, 404)


class AuthorTests(ForumTestData):
    def test_names(self):
        self.assertEqual(short_name(self.owner), "Kat W.")
        no_last = User.objects.create_user("sam", first_name="Sam")
        self.assertEqual(short_name(no_last), "Sam")
        self.assertEqual(initials(no_last), "SA")
        plain = User.objects.create_user("plainuser")
        self.assertEqual(short_name(plain), "plainuser")
        self.assertEqual(initials(plain), "PL")
        self.assertEqual(initials(self.owner), "KW")

    def test_deleted_accounts_stay_anonymous(self):
        gone = User.objects.create_user("gone", first_name="Gone", is_active=False)
        self.assertEqual(short_name(gone), "Deleted account")
        self.assertEqual(initials(gone), "?")
        post = self.post(gone, "Old post", "Still here")
        response = self.client.get(detail_url(post))
        self.assertContains(response, "Deleted account")
        self.assertNotContains(response, "Gone")

    def test_roles(self):
        self.assertEqual(role(self.owner), "Pet owner")
        self.assertEqual(role(self.sitter), "Caregiver")
        signed_up_as_caregiver = User.objects.create_user("newsitter")
        AccountProfile.objects.create(
            user=signed_up_as_caregiver, role=AccountProfile.Role.CAREGIVER
        )
        self.assertEqual(role(signed_up_as_caregiver), "Caregiver")
        self.assertEqual(role(User.objects.create_user("noprofile")), "Pet owner")
        admin = User.objects.create_user("admin", is_staff=True)
        self.assertEqual(role(admin), "Admin")

    def test_post_names_its_title(self):
        self.assertEqual(str(self.newer), "Best cafes for dogs")
