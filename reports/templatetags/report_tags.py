"""Small helpers for the admin Reports page (Kat's Figma, #95)."""

from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()


def _day(value):
    """'Today', 'Yesterday', or None for older dates."""
    today = timezone.localdate()
    day = timezone.localtime(value).date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return None


@register.filter
def when_short(value):
    """List rows: '1:05 PM' today, 'Yesterday', else 'Nov 3'."""
    if not value:
        return ""
    local = timezone.localtime(value)
    day = _day(value)
    if day == "Today":
        return date_format(local, "g:i A")
    return day or date_format(local, "M j")


@register.filter
def when_long(value):
    """Report header: 'Today, 1:05 PM', 'Yesterday, 6:40 PM', else 'Nov 3, 6:40 PM'."""
    if not value:
        return ""
    local = timezone.localtime(value)
    return f"{_day(value) or date_format(local, 'M j')}, {date_format(local, 'g:i A')}"


@register.filter
def posted_ago(value):
    """Review card: 'Posted today', 'Posted yesterday', else 'Posted Nov 3'."""
    if not value:
        return ""
    day = _day(value)
    return (
        f"Posted {day.lower()}"
        if day
        else f"Posted {date_format(timezone.localtime(value), 'M j')}"
    )
