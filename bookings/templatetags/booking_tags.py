from django import template

from bookings.views import owner_name, split_owner_bookings

register = template.Library()


@register.inclusion_tag("bookings/partials/request_panel_items.html", takes_context=True)
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
