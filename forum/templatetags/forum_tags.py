"""How long ago a post or comment was written, as in the Figma: "Just now",
"45m ago", "2h ago", "Yesterday", then the date ("Nov 8")."""

from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format

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
