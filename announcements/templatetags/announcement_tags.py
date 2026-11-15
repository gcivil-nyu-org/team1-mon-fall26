from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format

register = template.Library()


@register.filter
def day(moment):
    """ "Today", or "Nov 12" (with the year when it isn't this year)."""
    if not moment:
        return ""
    local = timezone.localtime(moment)
    today = timezone.localdate()
    if local.date() == today:
        return "Today"
    return date_format(local, "M j" if local.year == today.year else "M j, Y")
