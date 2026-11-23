"""#102 Remove Inappropriate Forum Content, as in Kat's Figma: admins open the
forum from Explore and remove spam or abusive posts and comments, after a
confirm popup. They're hidden from everyone."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from forum.models import Comment, Post

from .test_browse import LIST_URL, ForumTestData, detail_url

User = get_user_model()
EXPLORE_URL = reverse("places:explore")
MANAGE_URL = reverse("places:manage")


def remove_post_url(post):
    return reverse("forum:remove_post", args=[post.pk])


def remove_comment_url(comment):
    return reverse("forum:remove_comment", args=[comment.pk])


class RemoveTestData(ForumTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_user(
            "ada", password="pw-12345!", is_staff=True, first_name="Ada"
        )
        cls.spam = cls.post(cls.sitter, "Cheap pills here", "Buy now!!!", 0)
        cls.nice = Comment.objects.create(
            post=cls.newer, author=cls.sitter, body="Love Lucky Dog!"
        )
        cls.rude = Comment.objects.create(
            post=cls.newer, author=cls.sitter, body="What a dumb question"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def remove(self, item):
        item.removed_at = timezone.now()
        item.save()


class AdminForumTests(RemoveTestData):
    def test_admins_open_the_forum_from_explore(self):
        response = self.client.get(MANAGE_URL)
        self.assertContains(
            response, f'<a class="admin-tab" href="{LIST_URL}">Forum</a>'
        )
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{MANAGE_URL}" class="active">Explore</a>')
        self.assertContains(response, "<h1>Explore</h1>")
        self.assertContains(
            response,
            f'<a class="admin-tab is-active" href="{LIST_URL}" aria-current="page">'
            "Forum</a>",
        )
        # Admins look after the forum; they don't post or comment there.
        self.assertNotContains(response, reverse("forum:create"))
        self.assertNotContains(response, 'class="forum-comment-form"')

    def test_admins_see_remove_buttons(self):
        response = self.client.get(detail_url(self.newer))
        self.assertContains(response, f"remove_post={self.newer.pk}")
        self.assertContains(response, "Remove post")
        self.assertContains(response, f"remove_comment={self.nice.pk}")
        self.assertContains(response, f"remove_comment={self.rude.pk}")

    def test_no_comments_yet(self):
        response = self.client.get(detail_url(self.spam))
        self.assertContains(response, "No comments yet.</p>")

    def test_users_dont(self):
        self.client.force_login(self.owner)
        response = self.client.get(detail_url(self.newer))
        self.assertNotContains(response, "remove_post=")
        self.assertNotContains(response, "remove_comment=")
        self.assertNotContains(response, "admin-explore-tabs")
        self.assertContains(response, "<h1>Forum</h1>")


class ConfirmTests(RemoveTestData):
    def test_removing_a_post_asks_first(self):
        response = self.client.get(
            detail_url(self.spam) + f"&remove_post={self.spam.pk}"
        )
        self.assertContains(response, "Remove this post?")
        self.assertContains(
            response, "It will be hidden from everyone. This can’t be undone."
        )
        self.assertContains(response, "Remove post</button>")
        self.assertContains(response, f'action="{remove_post_url(self.spam)}"')
        self.assertContains(response, f'href="?post={self.spam.pk}">Cancel</a>')
        self.spam.refresh_from_db()
        self.assertIsNone(self.spam.removed_at)

    def test_removing_a_comment_asks_first(self):
        response = self.client.get(
            detail_url(self.newer) + f"&remove_comment={self.rude.pk}"
        )
        self.assertContains(response, "Remove this comment?")
        self.assertContains(response, "Remove comment</button>")
        self.assertContains(response, f'action="{remove_comment_url(self.rude)}"')

    def test_no_popup_for_removed_or_other_content(self):
        self.remove(self.rude)
        self.remove(self.spam)
        for query in (
            f"?post={self.newer.pk}&remove_comment={self.rude.pk}",
            f"?post={self.older.pk}&remove_comment={self.nice.pk}",
            f"?post={self.spam.pk}&remove_post={self.spam.pk}",
            f"?post={self.newer.pk}&remove_post={self.older.pk}",
            f"?post={self.newer.pk}&remove_post=abc",
        ):
            response = self.client.get(LIST_URL + query)
            self.assertNotContains(response, "modal-backdrop")

    def test_no_popup_for_users(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            detail_url(self.newer) + f"&remove_post={self.newer.pk}"
        )
        self.assertNotContains(response, "Remove this post?")


class RemovePostTests(RemoveTestData):
    def test_removing_a_post(self):
        response = self.client.post(remove_post_url(self.spam), follow=True)
        self.assertRedirects(response, LIST_URL + "?done=post_removed")
        self.assertContains(response, "Post removed. Users can no longer see it.")
        self.spam.refresh_from_db()
        self.assertIsNotNone(self.spam.removed_at)
        self.assertNotIn(self.spam, Post.objects.visible())
        # It's gone for admins too; the newest post that's still up opens.
        self.assertNotContains(response, "Cheap pills here")
        self.assertContains(
            response,
            '<h2 class="forum-title" id="forum-post-title">Best cafes for dogs</h2>',
        )

    def test_users_dont_see_a_removed_post(self):
        self.remove(self.spam)
        self.client.force_login(self.owner)
        response = self.client.get(LIST_URL)
        self.assertNotContains(response, "Cheap pills here")
        # Opening it shows the newest post that's still up instead.
        response = self.client.get(detail_url(self.spam))
        self.assertNotContains(response, "Cheap pills here")
        self.assertContains(response, "Best cafes for dogs")
        response = self.client.get(reverse("forum:detail", args=[self.spam.pk]))
        self.assertEqual(response.status_code, 404)
        # Or on Explore.
        response = self.client.get(EXPLORE_URL)
        self.assertNotContains(response, "Cheap pills here")

    def test_no_comments_on_a_removed_post(self):
        self.remove(self.spam)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("forum:comment", args=[self.spam.pk]), {"body": "Hi"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.spam.comments.exists())

    def test_removing_twice_keeps_the_first_time(self):
        self.remove(self.spam)
        when = Post.objects.get(pk=self.spam.pk).removed_at
        self.client.post(remove_post_url(self.spam))
        self.spam.refresh_from_db()
        self.assertEqual(self.spam.removed_at, when)

    def test_removed_banner_only_for_admins(self):
        self.client.force_login(self.owner)
        response = self.client.get(detail_url(self.newer) + "&done=post_removed")
        self.assertNotContains(response, "Post removed.")


class RemoveCommentTests(RemoveTestData):
    def test_removing_a_comment(self):
        response = self.client.post(remove_comment_url(self.rude), follow=True)
        self.assertRedirects(response, f"{detail_url(self.newer)}&done=comment_removed")
        self.assertContains(response, "Comment removed. Users can no longer see it.")
        self.rude.refresh_from_db()
        self.assertIsNotNone(self.rude.removed_at)
        # It's gone for admins too, and isn't counted.
        self.assertNotContains(response, "What a dumb question")
        self.assertContains(response, "1 comment<")
        self.nice.refresh_from_db()
        self.assertIsNone(self.nice.removed_at)

    def test_users_dont_see_a_removed_comment(self):
        self.remove(self.rude)
        self.client.force_login(self.owner)
        response = self.client.get(detail_url(self.newer))
        self.assertNotContains(response, "What a dumb question")
        self.assertContains(response, "Love Lucky Dog!")
        self.assertContains(response, "1 comment<")
        # The count in the list and on Explore leaves it out too.
        self.assertContains(response, '1<span class="visually-hidden"> comment<')
        response = self.client.get(EXPLORE_URL)
        self.assertContains(response, '1<span class="visually-hidden"> comment<')


class AccessTests(RemoveTestData):
    def test_only_admins_can_remove(self):
        for user in (self.owner, self.sitter):
            self.client.force_login(user)
            self.assertEqual(
                self.client.post(remove_post_url(self.spam)).status_code, 403
            )
            self.assertEqual(
                self.client.post(remove_comment_url(self.rude)).status_code, 403
            )
        self.spam.refresh_from_db()
        self.rude.refresh_from_db()
        self.assertIsNone(self.spam.removed_at)
        self.assertIsNone(self.rude.removed_at)

    def test_log_in_first(self):
        self.client.logout()
        url = remove_post_url(self.spam)
        response = self.client.post(url)
        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_remove_needs_a_post(self):
        self.assertEqual(self.client.get(remove_post_url(self.spam)).status_code, 405)
        self.assertEqual(
            self.client.get(remove_comment_url(self.rude)).status_code, 405
        )

    def test_missing_content(self):
        self.assertEqual(
            self.client.post(reverse("forum:remove_post", args=[999])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("forum:remove_comment", args=[999])).status_code,
            404,
        )
