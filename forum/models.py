"""Community forum (epic: Participate in Community Forum): posts that pet owners
and caregivers share with everyone on PawPal."""

from django.conf import settings
from django.db import models

TITLE_LENGTH = 120
BODY_LENGTH = 5000
COMMENT_LENGTH = 1000


class ForumQuerySet(models.QuerySet):
    def visible(self):
        """#102: what regular users see. Admins also see removed content."""
        return self.filter(removed_at__isnull=True)

    def pinned(self):
        """#104: posts an admin pinned, the most recently pinned first."""
        return self.filter(pinned_at__isnull=False).order_by("-pinned_at", "-pk")

    def unpinned(self):
        return self.filter(pinned_at__isnull=True)


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
    # #102: an admin removed it (spam or abuse). It's hidden from everyone
    # but admins, who still see it marked Removed.
    removed_at = models.DateTimeField(null=True, blank=True)
    # #104 Pin Helpful Forum Posts: an admin pinned it, so it shows at the top
    # of the forum for everyone (Kat's Figma "Pin Helpful Forum Posts").
    pinned_at = models.DateTimeField(null=True, blank=True)
    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = ForumQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    @property
    def is_pinned(self):
        return self.pinned_at is not None


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
    # #102: removed by an admin, like a removed post.
    removed_at = models.DateTimeField(null=True, blank=True)

    objects = ForumQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Comment by {self.author} on {self.post}"


RULE_TITLE_LENGTH = 80
RULE_TEXT_LENGTH = 300


class GuidelineQuerySet(models.QuerySet):
    def shown(self):
        """The rules everyone sees, in order. Removed ones stay in the
        database so "Last updated" still knows when one was removed."""
        return self.filter(removed_at__isnull=True).order_by("position", "pk")


class GuidelineRule(models.Model):
    """#105 Manage Community Guidelines: one numbered rule of the forum's
    community guidelines (Kat's Figma "Manage Community Guidelines"). Admins
    add, edit and remove rules; everyone reads them from the Forum."""

    title = models.CharField(max_length=RULE_TITLE_LENGTH)
    text = models.CharField(max_length=RULE_TEXT_LENGTH)
    position = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    objects = GuidelineQuerySet.as_manager()

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.title


def guidelines_updated_at():
    """When the guidelines last changed: a rule saved, added or removed."""
    latest = GuidelineRule.objects.aggregate(
        saved=models.Max("updated_at"), removed=models.Max("removed_at")
    )
    times = [t for t in latest.values() if t is not None]
    return max(times) if times else None
