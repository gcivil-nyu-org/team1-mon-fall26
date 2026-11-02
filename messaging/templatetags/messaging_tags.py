"""Times on the Messages page, written the way the design shows them."""

from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format

register = template.Library()


@register.filter
def inbox_time(moment):
    """ "12:16 PM" today, "Yesterday", "Oct 3", or "Oct 3, 2025" for older years."""
    if not moment:
        return ""
    local = timezone.localtime(moment)
    today = timezone.localdate()
    if local.date() == today:
        return date_format(local, "g:i A")
    if local.date() == today - timedelta(days=1):
        return "Yesterday"
    if local.year == today.year:
        return date_format(local, "M j")
    return date_format(local, "M j, Y")


@register.filter
def booking_when(moment):
    """ "Today · 12:00 PM" or "Sat, Oct 3 · 5:30 PM" for the booking card."""
    local = timezone.localtime(moment)
    if local.date() == timezone.localdate():
        return date_format(local, "\\T\\o\\d\\a\\y · g:i A")
    return date_format(local, "D, M j · g:i A")
