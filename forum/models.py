"""Community forum (epic: Participate in Community Forum): posts that pet owners
and caregivers share with everyone on PawPal."""

from django.conf import settings
from django.db import models

TITLE_LENGTH = 120
BODY_LENGTH = 5000


class Post(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forum_posts",
    )
    title = models.CharField(max_length=TITLE_LENGTH)
    body = models.TextField(max_length=BODY_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title
