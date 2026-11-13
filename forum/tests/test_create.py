"""#67 Create Forum Post, as in Kat's 11/12 Figma: New post opens a popup
over the Forum page with a title, a topic (Places, Tips or Questions) and the
details, all required. Once posted, the post is open with "Posted! Others can
now see and comment." and a NEW badge in the list."""

from django.urls import reverse

from forum.models import BODY_LENGTH, TITLE_LENGTH, Post

from .test_browse import LIST_URL, ForumTestData

CREATE_URL = reverse("forum:create")


class CreatePostTests(ForumTestData):
    def publish(self, **data):
        fields = {
            "title": "How do you keep dogs cool in summer?",
            "topic": "questions",
            "body": "My French bulldog gets tired fast on hot days.",
        }
        fields.update(data)
        return self.client.post(CREATE_URL, fields, follow=True)

    def test_log_in_first(self):
        self.client.logout()
        response = self.client.get(CREATE_URL)
        self.assertRedirects(response, f"{reverse('login')}?next={CREATE_URL}")
        self.client.post(CREATE_URL, {"title": "Hi", "topic": "tips", "body": "x"})
        self.assertEqual(Post.objects.count(), 2)

    def test_forum_links_to_the_popup(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{CREATE_URL}">')
        self.assertContains(response, "New post</a>")
        self.assertIsNone(response.context["post_form"])
        self.assertNotContains(response, 'role="dialog"')
        Post.objects.all().delete()
        response = self.client.get(LIST_URL)
        self.assertContains(response, f'href="{CREATE_URL}">Write a post</a>')

    def test_popup_over_the_forum(self):
        response = self.client.get(CREATE_URL)
        self.assertTemplateUsed(response, "forum/forum.html")
        self.assertContains(response, 'role="dialog"')
        self.assertContains(
            response, '<h2 id="new-post-title">New post</h2>', html=True
        )
        self.assertContains(response, 'placeholder="What’s it about?"')
        self.assertContains(
            response, 'placeholder="Share a spot, a tip, or ask a question"'
        )
        for label in ("Places", "Tips", "Questions"):
            self.assertContains(response, f"<span>{label}</span>", html=True)
        self.assertNotContains(response, "checked")
        self.assertContains(response, f'href="{LIST_URL}" data-close-popup>Cancel</a>')
        self.assertContains(response, ">Post</button>")
        self.assertNotContains(response, "Almost there.")
        # The forum is still behind it.
        self.assertContains(response, "Best cafes for dogs")

    def test_posts_and_opens_the_post(self):
        response = self.publish(
            title="  How do you keep dogs cool in summer?  ", body=" Tips? "
        )
        post = Post.objects.get(title="How do you keep dogs cool in summer?")
        self.assertEqual(post.author, self.owner)
        self.assertEqual(post.topic, "questions")
        self.assertEqual(post.body, "Tips?")
        self.assertRedirects(response, f"{LIST_URL}?post={post.pk}")
        self.assertEqual(response.context["selected"], post)
        self.assertContains(
            response, "<strong>Posted!</strong> Others can now see and comment."
        )
        self.assertContains(response, '<span class="forum-new-badge">New</span>')
        self.assertContains(response, "No comments yet. Be the first!")
        self.assertEqual(list(response.context["page"])[0], post)

        # Only right after posting.
        again = self.client.get(f"{LIST_URL}?post={post.pk}")
        self.assertNotContains(again, "Posted!")
        self.assertNotContains(again, "forum-new-badge")

    def test_caregivers_can_post_too(self):
        self.client.force_login(self.sitter)
        self.publish(title="Available this weekend", topic="tips")
        post = Post.objects.get(title="Available this weekend")
        self.assertEqual(post.author, self.sitter)
        response = self.client.get(f"{LIST_URL}?post={post.pk}")
        self.assertContains(response, "Caregiver · ")

    def test_required_fields(self):
        response = self.publish(title="   ", topic="", body="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="dialog"')
        self.assertContains(
            response, "<strong>Almost there.</strong> Fill in the required fields."
        )
        self.assertContains(response, "Add a title.")
        self.assertContains(response, "Pick a topic.")
        self.assertContains(response, "Add some details.")
        self.assertEqual(Post.objects.count(), 2)

    def test_unknown_topic(self):
        response = self.publish(topic="gossip")
        self.assertContains(response, "Pick a topic.")
        self.assertEqual(Post.objects.count(), 2)

    def test_whats_typed_stays_when_something_is_missing(self):
        response = self.publish(title="", topic="places", body="My draft")
        self.assertContains(response, "My draft</textarea>")
        self.assertContains(response, 'value="places" id="id_topic_0" required checked')

    def test_length_limits(self):
        response = self.publish(
            title="t" * (TITLE_LENGTH + 1), body="b" * (BODY_LENGTH + 1)
        )
        self.assertContains(
            response, f"Keep the title under {TITLE_LENGTH} characters."
        )
        self.assertContains(response, f"Keep it under {BODY_LENGTH} characters.")
        self.assertEqual(Post.objects.count(), 2)
