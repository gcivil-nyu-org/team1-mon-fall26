from django.utils.functional import SimpleLazyObject

from .models import Announcement


def current_announcement(request):
    """The banner at the top of the page: the newest published announcement
    for this user that they haven't closed. Admins write them, so they don't
    get the banner."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or user.is_staff:
        return {}

    def newest():
        return (
            Announcement.objects.for_user(user).exclude(dismissals__user=user).first()
        )

    return {"current_announcement": SimpleLazyObject(newest)}
