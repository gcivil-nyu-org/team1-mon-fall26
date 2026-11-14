"""Community forum (epic: Participate in Community Forum): posts that pet owners
and caregivers share with everyone on PawPal."""

from django.conf import settings
from django.db import models

TITLE_LENGTH = 120
BODY_LENGTH = 5000
COMMENT_LENGTH = 1000


class Post(models.Model):
    class Topic(models.TextChoices):
        # The topic chips on the Forum page (Kat's 11/12 Figma).
        PLACES = "places", "Places"
        TIPS = "tips", "Tips"
        QUESTIONS = "questions", "Questions"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_posts",
    )
    title = models.CharField(max_length=TITLE_LENGTH)
    topic = models.CharField(max_length=20, choices=Topic.choices, default=Topic.TIPS)
    body = models.TextField(max_length=BODY_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title


class Comment(models.Model):
    """#69 Comment on Forum Posts: replies under a post, oldest first."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_comments",
    )
    body = models.TextField(max_length=COMMENT_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Comment by {self.author} on {self.post}"
