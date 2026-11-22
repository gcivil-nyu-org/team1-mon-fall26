"""#104 Pin Helpful Forum Posts, as in Kat's Figma "Pin Helpful Forum Posts"
and "Unpin Forum Posts": an admin pins a helpful post so it shows under
"Pinned" at the top of the forum for everyone, and can unpin it again."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from forum.models import Post
from forum.templatetags.forum_tags import forum_strip
from forum.views import PER_PAGE

from .test_browse import LIST_URL, ForumTestData, detail_url

User = get_user_model()


def pin_url(post):
    return reverse("forum:pin_post", args=[post.pk])


def unpin_url(post):
    return reverse("forum:unpin_post", args=[post.pk])


class PinTestData(ForumTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_user(
            "ada", password="pw-12345!", is_staff=True, first_name="Ada"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def pin(self, post):
        post.pinned_at = timezone.now()
        post.save()


class PinTests(PinTestData):
    def test_admins_see_pin_post(self):
        response = self.client.get(detail_url(self.older))
        self.assertContains(response, f'action="{pin_url(self.older)}"')
        self.assertContains(response, "Pin post</button>")
        self.assertNotContains(response, "Unpin post")

    def test_pin_a_post(self):
        response = self.client.post(pin_url(self.older))
        self.assertRedirects(
            response,
            f"{detail_url(self.older)}&done=pinned",
            fetch_redirect_response=False,
        )
        self.older.refresh_from_db()
        self.assertTrue(self.older.is_pinned)
        self.assertEqual(self.older.pinned_by, self.admin)

        response = self.client.get(response.url)
        self.assertContains(
            response, "Post pinned. It now shows at the top of the forum."
        )
        # Figma: "PINNED" above "RECENT", the post with a pin, a Pinned pill
        # in the post and Unpin post instead of Pin post.
        self.assertEqual(response.context["pinned"], [self.older])
        self.assertEqual(list(response.context["page"]), [self.newer])
        self.assertContains(response, '<h2 class="forum-eyebrow" id="forum-pinned">')
        self.assertContains(response, 'class="forum-pin-badge"')
        self.assertContains(response, 'class="forum-pinned-pill"')
        self.assertContains(response, f'action="{unpin_url(self.older)}"')

    def test_pinning_twice_keeps_the_first_time(self):
        self.client.post(pin_url(self.older))
        self.older.refresh_from_db()
        first = self.older.pinned_at
        self.client.post(pin_url(self.older))
        self.older.refresh_from_db()
        self.assertEqual(self.older.pinned_at, first)

    def test_unpin_a_post(self):
        self.pin(self.older)
        response = self.client.post(unpin_url(self.older))
        self.assertRedirects(
            response,
            f"{detail_url(self.older)}&done=unpinned",
            fetch_redirect_response=False,
        )
        self.older.refresh_from_db()
        self.assertFalse(self.older.is_pinned)
        self.assertIsNone(self.older.pinned_by)
        response = self.client.get(response.url)
        self.assertContains(
            response, "Post unpinned. It no longer shows at the top of the forum."
        )
        self.assertEqual(response.context["pinned"], [])
        self.assertEqual(list(response.context["page"]), [self.newer, self.older])
        # Unpinning again does nothing.
        self.client.post(unpin_url(self.older))
        self.older.refresh_from_db()
        self.assertFalse(self.older.is_pinned)

    def test_only_posts_still_up_can_be_pinned(self):
        self.older.removed_at = timezone.now()
        self.older.save()
        self.assertEqual(self.client.post(pin_url(self.older)).status_code, 404)
        self.assertEqual(self.client.post(pin_url(Post(pk=999))).status_code, 404)

    def test_pin_only_by_post(self):
        self.assertEqual(self.client.get(pin_url(self.older)).status_code, 405)
        self.assertEqual(self.client.get(unpin_url(self.older)).status_code, 405)

    def test_regular_users_cannot_pin(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(pin_url(self.older)).status_code, 403)
        self.pin(self.older)
        self.assertEqual(self.client.post(unpin_url(self.older)).status_code, 403)
        self.older.refresh_from_db()
        self.assertTrue(self.older.is_pinned)


class EveryoneSeesPinnedTests(PinTestData):
    def setUp(self):
        self.client.force_login(self.owner)

    def test_pinned_posts_come_first_for_users(self):
        self.pin(self.older)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["pinned"], [self.older])
        # The forum opens on the pinned post.
        self.assertEqual(response.context["selected"], self.older)
        self.assertContains(response, "Pinned</span>")
        self.assertNotContains(response, "Pin post")
        self.assertNotContains(response, "done=pinned")
        # Users don't see the admin banner, even with ?done=.
        response = self.client.get(f"{detail_url(self.older)}&done=pinned")
        self.assertNotContains(response, "Post pinned.")

    def test_newest_pinned_first(self):
        self.pin(self.older)
        self.pin(self.newer)
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["pinned"], [self.newer, self.older])
        self.assertEqual(list(response.context["page"]), [])
        self.assertNotContains(response, 'id="forum-recent"')

    def test_topics_filter_pinned_posts_too(self):
        self.pin(self.older)
        response = self.client.get(LIST_URL, {"topic": "places"})
        self.assertEqual(response.context["pinned"], [])
        self.assertEqual(list(response.context["page"]), [self.newer])
        response = self.client.get(LIST_URL, {"topic": "questions"})
        self.assertEqual(response.context["pinned"], [self.older])

    def test_pinned_posts_only_on_the_first_page(self):
        for n in range(PER_PAGE):
            self.post(self.owner, f"Post {n}", "Hi", 3)
        self.pin(self.older)
        response = self.client.get(LIST_URL, {"page": 2})
        self.assertEqual(response.context["pinned"], [])

    def test_removed_pinned_posts_are_hidden(self):
        self.pin(self.older)
        self.older.removed_at = timezone.now()
        self.older.save()
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["pinned"], [])

    def test_explore_shows_pinned_posts_first(self):
        self.pin(self.older)
        posts = forum_strip()["posts"]
        self.assertEqual(posts, [self.older, self.newer])
        response = self.client.get(reverse("places:explore"))
        self.assertContains(response, 'class="forum-pinned-pill"')
