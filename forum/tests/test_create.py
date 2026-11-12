"""#67 Create Forum Post: pet owners and caregivers write a post with a title
and content; it's published and shows up in the forum. Neither field can be
left blank."""

from django.urls import reverse

from forum.models import BODY_LENGTH, TITLE_LENGTH, Post

from .test_browse import LIST_URL, ForumTestData

CREATE_URL = reverse("forum:create")


class CreatePostTests(ForumTestData):
    def publish(self, **data):
        fields = {"title": "Vet near Prospect Park?", "body": "Looking for one."}
        fields.update(data)
        return self.client.post(CREATE_URL, fields, follow=True)

    def test_log_in_first(self):
        self.client.logout()
        response = self.client.get(CREATE_URL)
        self.assertRedirects(response, f"{reverse('login')}?next={CREATE_URL}")
        self.client.post(CREATE_URL, {"title": "Hi", "body": "There"})
        self.assertEqual(Post.objects.count(), 2)

    def test_forum_links_to_the_form(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{CREATE_URL}">New post</a>')
        Post.objects.all().delete()
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{CREATE_URL}">Write a post</a>')

    def test_form(self):
        response = self.client.get(CREATE_URL)
        self.assertContains(response, "<h1>New post</h1>", html=True)
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="body"')
        self.assertContains(response, f"0/{BODY_LENGTH}")
        self.assertContains(response, "Publish post")
        self.assertContains(response, f'href="{LIST_URL}">Cancel</a>')
        self.assertNotContains(response, "Almost there.")

    def test_publishes_the_post_and_shows_it(self):
        response = self.publish(title="  Vet near Prospect Park?  ", body=" Help! ")
        post = Post.objects.get(title="Vet near Prospect Park?")
        self.assertEqual(post.author, self.owner)
        self.assertEqual(post.body, "Help!")
        self.assertRedirects(response, reverse("forum:detail", args=[post.pk]))
        self.assertContains(response, "Your post is published.")
        self.assertContains(response, "Vet near Prospect Park?")

        # Newest first in the forum.
        forum = self.client.get(LIST_URL)
        self.assertEqual(list(forum.context["page"])[0], post)

    def test_caregivers_can_post_too(self):
        self.client.force_login(self.sitter)
        self.publish(title="Available this weekend")
        post = Post.objects.get(title="Available this weekend")
        self.assertEqual(post.author, self.sitter)
        response = self.client.get(LIST_URL)
        self.assertContains(response, "Caregiver")

    def test_required_fields(self):
        response = self.publish(title="   ", body="")
        self.assertContains(response, "Almost there.")
        self.assertContains(response, "Enter a title.")
        self.assertContains(response, "Write your post.")
        self.assertEqual(Post.objects.count(), 2)

    def test_whats_typed_stays_when_something_is_missing(self):
        response = self.publish(title="", body="My draft")
        self.assertContains(response, "My draft</textarea>")
        self.assertContains(response, "8/5000")

    def test_length_limits(self):
        response = self.publish(
            title="t" * (TITLE_LENGTH + 1), body="b" * (BODY_LENGTH + 1)
        )
        self.assertContains(
            response, f"Keep the title under {TITLE_LENGTH} characters."
        )
        self.assertContains(response, f"Keep your post under {BODY_LENGTH} characters.")
        self.assertEqual(Post.objects.count(), 2)
