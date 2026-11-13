"""#68 Browse Forum Posts, as in Kat's 11/12 Figma: the Forum page (under
Explore) lists recent posts on the left, newest first, each with its title,
author, time, topic and comment count, and shows the selected post in full
on the right. Topic chips filter the list."""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from forum.authors import initials, role, short_name
from forum.models import Post
from forum.templatetags.forum_tags import ago
from forum.views import PER_PAGE

User = get_user_model()
LIST_URL = reverse("forum:list")


def detail_url(post):
    """The Forum page with this post open."""
    return f"{LIST_URL}?post={post.pk}"


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
        cls.older = cls.post(
            cls.sitter, "Quiet dog runs?", "Any in Park Slope?", 2, "questions"
        )
        cls.newer = cls.post(
            cls.owner,
            "Best cafes for dogs",
            "Lucky Dog has water bowls.\n\nThey also sell treats.",
            1,
            "places",
        )

    @classmethod
    def post(cls, author, title, body, days_ago=0, topic="tips"):
        post = Post.objects.create(author=author, title=title, body=body, topic=topic)
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
        for url in (LIST_URL, reverse("forum:detail", args=[self.newer.pk])):
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_forum_is_under_explore(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'class="active">Explore</a>')
        self.assertNotContains(response, ">Forum</a>")
        self.assertContains(response, f'href="{reverse("places:explore")}"')
        self.assertContains(response, "Pet-friendly places")

    def test_caregivers_get_explore_too(self):
        self.client.force_login(self.sitter)
        explore = reverse("places:explore")
        response = self.client.get(reverse("messaging:inbox"))
        self.assertContains(response, f'href="{explore}" class="">Explore</a>')
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{explore}" class="active">Explore</a>')

    def test_old_post_links_open_the_post_on_the_forum_page(self):
        response = self.client.get(reverse("forum:detail", args=[self.older.pk]))
        self.assertRedirects(response, detail_url(self.older))
        missing = self.client.get(reverse("forum:detail", args=[9999]))
        self.assertEqual(missing.status_code, 404)


class ListTests(ForumTestData):
    def test_recent_posts_newest_first_with_basic_information(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(list(response.context["page"]), [self.newer, self.older])
        for text in (
            "Recent",
            "Best cafes for dogs",
            "Kat W. · Yesterday",
            "Quiet dog runs?",
            "Chloe S. · ",
            '<span class="forum-tag forum-tag-places">Places</span>',
            '<span class="forum-tag forum-tag-questions">Questions</span>',
        ):
            self.assertContains(response, text, html=text.startswith("<"))

    def test_each_post_opens_on_the_right(self):
        response = self.client.get(LIST_URL)
        for post in (self.newer, self.older):
            self.assertContains(response, f'href="?post={post.pk}"')

    def test_newest_post_is_open_first(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["selected"], self.newer)
        self.assertContains(
            response, f'class="forum-row is-selected" href="?post={self.newer.pk}"'
        )

    def test_pages_of_posts(self):
        for i in range(PER_PAGE):
            self.post(self.owner, f"Post {i}", "Hello")
        first = self.client.get(LIST_URL)
        self.assertEqual(len(first.context["page"]), PER_PAGE)
        self.assertContains(first, "Page 1 of 2")
        self.assertContains(first, 'href="?page=2">Older')
        second = self.client.get(LIST_URL, {"page": 2})
        self.assertEqual(list(second.context["page"]), [self.newer, self.older])
        self.assertContains(second, 'href="?page=1">Newer')
        self.assertContains(second, f'href="?page=2&amp;post={self.older.pk}"')

    def test_no_posts_yet(self):
        Post.objects.all().delete()
        response = self.client.get(LIST_URL)
        self.assertContains(response, "No posts yet")
        self.assertIsNone(response.context["selected"])
        self.assertNotContains(response, "Page 1")


class TopicTests(ForumTestData):
    def test_topic_chips(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(
            [(t["label"], t["active"]) for t in response.context["topics"]],
            [("All", True), ("Places", False), ("Tips", False), ("Questions", False)],
        )
        self.assertContains(response, f'href="{LIST_URL}?topic=tips"')

    def test_filter_by_topic(self):
        response = self.client.get(LIST_URL, {"topic": "questions"})
        self.assertEqual(list(response.context["page"]), [self.older])
        self.assertEqual(response.context["selected"], self.older)
        self.assertContains(
            response, f'href="?topic=questions&amp;post={self.older.pk}"'
        )
        active = [t["label"] for t in response.context["topics"] if t["active"]]
        self.assertEqual(active, ["Questions"])

    def test_topic_with_no_posts(self):
        response = self.client.get(LIST_URL, {"topic": "tips"})
        self.assertContains(response, "No posts in this topic yet")

    def test_unknown_topic_shows_all(self):
        response = self.client.get(LIST_URL, {"topic": "nope"})
        self.assertEqual(len(response.context["page"]), 2)
        self.assertEqual(Post.Topic.TIPS, Post._meta.get_field("topic").default)


class SelectedPostTests(ForumTestData):
    def test_shows_the_whole_post(self):
        response = self.client.get(detail_url(self.older))
        self.assertEqual(response.context["selected"], self.older)
        self.assertContains(response, "<title>Quiet dog runs? · Forum · PawPal</title>")
        self.assertContains(
            response,
            '<h2 class="forum-title" id="forum-post-title">Quiet dog runs?</h2>',
            html=True,
        )
        self.assertContains(response, "Chloe S.")
        self.assertContains(response, "Caregiver · ")
        self.assertContains(response, "<p>Any in Park Slope?</p>", html=True)

    def test_paragraphs(self):
        response = self.client.get(detail_url(self.newer))
        self.assertContains(response, "<p>Lucky Dog has water bowls.</p>", html=True)
        self.assertContains(response, "<p>They also sell treats.</p>", html=True)

    def test_unknown_or_bad_post_opens_the_newest(self):
        for value in ("9999", "abc"):
            response = self.client.get(LIST_URL, {"post": value})
            self.assertEqual(response.context["selected"], self.newer)

    def test_text_is_escaped(self):
        post = self.post(self.owner, "<b>Hi</b>", "<script>alert(1)</script>")
        response = self.client.get(detail_url(post))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;b&gt;Hi&lt;/b&gt;")


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
        post = self.post(admin, "From the team", "Hello")
        response = self.client.get(detail_url(post))
        self.assertContains(response, "forum-avatar-admin")

    def test_post_names_its_title(self):
        self.assertEqual(str(self.newer), "Best cafes for dogs")


class AgoTests(SimpleTestCase):
    """How long ago, as in the Figma ("Just now", "45m ago", "2h ago",
    "Yesterday", "Nov 8")."""

    now = datetime(2026, 11, 12, 18, 0, tzinfo=dt_timezone.utc)

    def test_ago(self):
        for delta, expected in (
            (timedelta(seconds=30), "Just now"),
            (timedelta(minutes=45), "45m ago"),
            (timedelta(hours=2), "2h ago"),
            (timedelta(days=1, hours=1), "Yesterday"),
            (timedelta(days=4), "Nov 8"),
            (timedelta(days=400), "Oct 8, 2025"),
        ):
            self.assertEqual(ago(self.now - delta, self.now), expected)

    def test_nothing(self):
        self.assertEqual(ago(None), "")
