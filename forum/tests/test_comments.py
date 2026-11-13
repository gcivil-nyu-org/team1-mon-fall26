"""#69 Comment on Forum Posts: on the selected post, pet owners and caregivers
write a comment; it shows under that post (and only that post) for everyone.
As in the Figma's "Comment posted" frame, the new comment is highlighted."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from forum.models import COMMENT_LENGTH, Comment

from .test_browse import LIST_URL, ForumTestData, detail_url

User = get_user_model()


def comment_url(post):
    return reverse("forum:comment", args=[post.pk])


class CommentTests(ForumTestData):
    def comment(self, post, body="Try Hillside Dog Park!", **kwargs):
        return self.client.post(comment_url(post), {"body": body}, **kwargs)

    def test_post_page_has_a_comment_box(self):
        response = self.client.get(detail_url(self.newer))
        self.assertContains(response, "0 comments")
        self.assertContains(response, "No comments yet.")
        self.assertContains(response, f'action="{comment_url(self.newer)}"')
        self.assertContains(response, 'placeholder="Add a comment…"')
        self.assertContains(response, 'class="btn forum-comment-button is-empty"')
        self.assertContains(response, "No comments yet. Be the first!")

    def test_comment_shows_under_the_post(self):
        response = self.comment(self.newer, "  Try Hillside Dog Park!  ")
        comment = Comment.objects.get()
        self.assertEqual(comment.post, self.newer)
        self.assertEqual(comment.author, self.owner)
        self.assertEqual(comment.body, "Try Hillside Dog Park!")
        landing = f"{detail_url(self.newer)}&new_comment={comment.pk}"
        self.assertRedirects(response, f"{landing}#comment-{comment.pk}")

        page = self.client.get(landing)
        self.assertContains(page, "1 comment<")
        self.assertContains(
            page, f'class="forum-comment is-new" id="comment-{comment.pk}"'
        )
        self.assertContains(page, "Try Hillside Dog Park!")
        self.assertContains(page, 'Kat W.</strong> <span class="muted">· Just now')
        self.assertNotContains(page, "No comments yet.")

        # Opened again later, it isn't highlighted.
        later = self.client.get(detail_url(self.newer))
        self.assertContains(later, f'class="forum-comment" id="comment-{comment.pk}"')

    def test_others_see_it_with_who_wrote_it(self):
        self.comment(self.newer)
        self.client.force_login(self.sitter)
        self.comment(self.newer, "Thanks, adding it to my list.")

        stranger = User.objects.create_user("sam")
        self.client.force_login(stranger)
        page = self.client.get(detail_url(self.newer))
        self.assertContains(page, "2 comments")
        self.assertEqual(
            [c.body for c in page.context["comments"]],
            ["Try Hillside Dog Park!", "Thanks, adding it to my list."],
        )
        self.assertContains(page, "Kat W.")
        self.assertContains(page, "Chloe S.")
        # Caregivers' initials are on blue, as everywhere on PawPal.
        self.assertContains(page, "forum-avatar-caregiver forum-avatar-small")

    def test_comments_stay_with_their_post(self):
        self.comment(self.newer)
        other = self.client.get(detail_url(self.older))
        self.assertNotContains(other, "Try Hillside Dog Park!")
        self.assertContains(other, "0 comments")

    def test_forum_shows_how_many_comments(self):
        self.comment(self.newer)
        self.comment(self.newer, "Me too")
        response = self.client.get(LIST_URL)
        counts = [post.comment_count for post in response.context["page"]]
        self.assertEqual(counts, [2, 0])
        self.assertContains(response, '2<span class="visually-hidden"> comments</span>')
        self.assertContains(response, '0<span class="visually-hidden"> comments</span>')

    def test_empty_comment_is_refused(self):
        response = self.comment(self.newer, "   ")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Write a comment first.")
        self.assertContains(response, "Best cafes for dogs")
        self.assertEqual(response.context["selected"], self.newer)
        self.assertFalse(Comment.objects.exists())

    def test_comment_on_an_older_post_keeps_it_open(self):
        response = self.comment(self.older, "", follow=False)
        self.assertEqual(response.context["selected"], self.older)

    def test_long_comment_is_refused_and_kept(self):
        response = self.comment(self.newer, "x" * (COMMENT_LENGTH + 1))
        self.assertContains(
            response, f"Keep your comment under {COMMENT_LENGTH} characters."
        )
        self.assertContains(response, 'value="' + "x" * (COMMENT_LENGTH + 1) + '"')
        self.assertEqual(response.context["selected"], self.newer)
        self.assertFalse(Comment.objects.exists())

    def test_text_is_escaped(self):
        self.comment(self.newer, "<script>alert(1)</script>")
        page = self.client.get(detail_url(self.newer))
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;")

    def test_log_in_first(self):
        self.client.logout()
        response = self.comment(self.newer)
        url = comment_url(self.newer)
        self.assertRedirects(response, f"{reverse('login')}?next={url}")
        self.assertFalse(Comment.objects.exists())

    def test_only_by_posting(self):
        self.assertEqual(self.client.get(comment_url(self.newer)).status_code, 405)

    def test_unknown_post_is_404(self):
        response = self.client.post(
            reverse("forum:comment", args=[9999]), {"body": "Hi"}
        )
        self.assertEqual(response.status_code, 404)

    def test_comment_names_its_post(self):
        self.comment(self.newer)
        self.assertEqual(
            str(Comment.objects.get()), "Comment by kat on Best cafes for dogs"
        )
