from django import template
from django.utils import dateformat, timezone

from bookings.views import owner_name, split_owner_bookings

register = template.Library()


@register.inclusion_tag(
    "bookings/partials/request_panel_items.html", takes_context=True
)
def my_booking_requests(context, limit=3):
    """The owner's upcoming and past requests, for the "My booking requests" panel."""
    user = context["request"].user
    if not user.is_authenticated:
        return {"upcoming": [], "past": []}
    upcoming, past = split_owner_bookings(user)
    return {"upcoming": upcoming[:limit], "past": past[:limit]}


@register.filter
def short_name(user):
    """A user's name as "Kat W.", falling back to their username."""
    return owner_name(user)


@register.filter
def first_name(user):
    """A user's first name, falling back to their username."""
    return (user.first_name or "").strip() or user.username


def _format(value, fmt):
    """`value` in local time with the date format `fmt`, adding the year when
    it isn't this year, so a date in 2140 doesn't look like next week (#331)."""
    local = timezone.localtime(value)
    if local.year != timezone.localdate().year:
        fmt = fmt.replace("M j", "M j, Y", 1)
    return dateformat.format(local, fmt)


@register.filter
def care_date(value, fmt="D, M j, g:i A"):
    """A booking or care post time, with the year when it's not this year."""
    if not value:
        return ""
    return _format(value, fmt)


@register.filter
def care_span(booking):
    """ "Sat, Nov 21, 7:08 PM – 10:08 PM", or with the end date when the care
    runs into another day (#318)."""
    start = timezone.localtime(booking.start_time)
    end = timezone.localtime(booking.end_time)
    first = _format(start, "D, M j, g:i A")
    if start.date() == end.date():
        return f"{first} – {dateformat.format(end, 'g:i A')}"
    return f"{first} – {_format(end, 'D, M j, g:i A')}"
