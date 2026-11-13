"""How long ago a post or comment was written, as in the Figma: "Just now",
"45m ago", "2h ago", "Yesterday", then the date ("Nov 8"). Also "From the forum" on Explore.
"""

from datetime import timedelta

from django import template
from django.db.models import Count
from django.utils import timezone
from django.utils.dateformat import format as date_format

from ..authors import describe
from ..models import Post

register = template.Library()


@register.filter
def ago(value, now=None):
    if not value:
        return ""
    now = now or timezone.now()
    seconds = (now - value).total_seconds()
    if seconds < 60:
        return "Just now"
    if seconds < 60 * 60:
        return f"{int(seconds // 60)}m ago"
    if seconds < 24 * 60 * 60:
        return f"{int(seconds // 3600)}h ago"
    local = timezone.localtime(value)
    today = timezone.localtime(now).date()
    if local.date() == today - timedelta(days=1):
        return "Yesterday"
    if local.year == today.year:
        return date_format(local, "M j")
    return date_format(local, "M j, Y")


@register.inclusion_tag("forum/partials/explore_strip.html")
def forum_strip(count=3):
    """'From the forum' on the Explore page (Figma "Explore (Pet owner)"):
    the newest posts, or a nudge to write the first one."""
    posts = (
        Post.objects.select_related(
            "author", "author__account_profile", "author__caregiver_profile"
        )
        .annotate(comment_count=Count("comments"))
        .order_by("-created_at", "-pk")[:count]
    )
    return {"posts": [describe(post) for post in posts]}
