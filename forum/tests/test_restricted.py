"""#103 Restrict Forum Posting (Kat's Figma "Restricted User"): an account
whose forum posting an admin restricted can still read the forum and use the
rest of PawPal, but can't write posts or comments until an admin restores
it. Admins can restrict a post's author from the forum."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.restriction import restore_forum, restrict_forum
from forum.models import Comment, Post

from .test_browse import LIST_URL, ForumTestData, detail_url

CREATE_URL = reverse("forum:create")
NOTE = "You can’t post or comment in the forum right now."


class RestrictedPostingTests(ForumTestData):
    def setUp(self):
        super().setUp()
        restrict_forum(self.owner)

    def test_they_can_still_read_the_forum(self):
        response = self.client.get(detail_url(self.older))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quiet dog runs?")
        self.assertContains(response, NOTE)
        # New post is greyed out, and there's no comment box.
        self.assertNotContains(response, f'href="{CREATE_URL}"')
        self.assertContains(response, "forum-new is-disabled")
        self.assertNotContains(response, 'class="forum-comment-form"')

    def test_they_cant_post(self):
        response = self.client.get(CREATE_URL)
        self.assertRedirects(response, LIST_URL)
        response = self.client.post(
            CREATE_URL,
            {"title": "Hi", "topic": "tips", "body": "Hello"},
            follow=True,
        )
        self.assertRedirects(response, LIST_URL)
        self.assertContains(response, NOTE)
        self.assertFalse(Post.objects.filter(title="Hi").exists())

    def test_they_cant_comment(self):
        response = self.client.post(
            reverse("forum:comment", args=[self.older.pk]), {"body": "Spam"}
        )
        self.assertRedirects(response, detail_url(self.older))
        self.assertFalse(Comment.objects.exists())

    def test_no_write_a_post_button_on_an_empty_topic(self):
        response = self.client.get(LIST_URL + "?topic=tips")
        self.assertContains(response, "No posts in this topic yet")
        self.assertNotContains(response, "Write a post")

    def test_the_rest_of_pawpal_still_works(self):
        for name in ("pets:list", "places:explore", "messaging:inbox"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_other_accounts_can_still_post(self):
        self.client.force_login(self.sitter)
        response = self.client.get(detail_url(self.older))
        self.assertNotContains(response, NOTE)
        self.assertContains(response, f'href="{CREATE_URL}"')
        self.client.post(
            reverse("forum:comment", args=[self.older.pk]), {"body": "Try Hillside"}
        )
        self.assertTrue(Comment.objects.filter(author=self.sitter).exists())

    def test_restored_accounts_can_post_again(self):
        restore_forum(self.owner)
        response = self.client.get(detail_url(self.older))
        self.assertNotContains(response, NOTE)
        self.client.post(
            CREATE_URL, {"title": "Back!", "topic": "tips", "body": "Hello again"}
        )
        self.assertTrue(Post.objects.filter(title="Back!").exists())


class RestrictFromForumTests(ForumTestData):
    """On the Forum page, admins see Restrict posting next to Remove post."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user("ada", is_staff=True)
        self.client.force_login(self.admin)

    def test_restrict_posting_opens_the_authors_account(self):
        response = self.client.get(detail_url(self.older))
        url = reverse("staff:user_detail", args=[self.sitter.pk])
        self.assertContains(response, f'href="{url}?confirm=forum"')
        self.assertContains(response, "Restrict posting")

    def test_not_for_authors_already_restricted(self):
        restrict_forum(self.sitter)
        response = self.client.get(detail_url(self.older))
        self.assertNotContains(response, "Restrict posting")
