"""'From the forum' on the Explore page (Kat's 11/12 Figma "Explore (Pet
owner)", "Explore (Caregiver)" and "Explore (No post)"): the three newest
posts with See all, or a nudge to write the first post."""

from django.urls import reverse

from forum.models import Comment, Post

from .test_browse import LIST_URL, ForumTestData

EXPLORE_URL = reverse("places:explore")


class ExploreStripTests(ForumTestData):
    def test_newest_posts_on_explore(self):
        newest = self.post(self.sitter, "Pup cups at Bark & Brew", "Yes!", 0, "places")
        Comment.objects.create(post=newest, author=self.owner, body="Love it")
        response = self.client.get(EXPLORE_URL)
        self.assertContains(response, "From the forum")
        self.assertContains(response, f'href="{LIST_URL}">See all')
        for post in (newest, self.newer, self.older):
            self.assertContains(response, f'href="{LIST_URL}?post={post.pk}"')
        self.assertContains(response, "Pup cups at Bark &amp; Brew")
        self.assertContains(response, "Chloe S. · Just now")
        self.assertContains(response, '1<span class="visually-hidden"> comment</span>')

    def test_only_three(self):
        for i in range(3):
            self.post(self.owner, f"Post {i}", "Hello")
        response = self.client.get(EXPLORE_URL)
        self.assertContains(response, "Post 2")
        self.assertNotContains(response, "Best cafes for dogs")
        self.assertNotContains(response, "Quiet dog runs?")

    def test_no_posts_yet(self):
        Post.objects.all().delete()
        response = self.client.get(EXPLORE_URL)
        self.assertContains(response, "No posts yet")
        self.assertContains(
            response, "Know a great pet-friendly spot? Be the first to share it."
        )
        self.assertContains(response, f'href="{reverse("forum:create")}"')
        self.assertContains(response, "Create a post")
        self.assertNotContains(response, "See all")

    def test_caregivers_see_it_too(self):
        self.client.force_login(self.sitter)
        response = self.client.get(EXPLORE_URL)
        self.assertContains(response, "From the forum")
        self.assertContains(response, "Best cafes for dogs")
