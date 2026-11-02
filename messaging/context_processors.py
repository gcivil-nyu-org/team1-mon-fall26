from django.utils.functional import SimpleLazyObject

from .inbox import unread_count


def unread_messages(request):
    """The number on the Messages tab: conversations with unread messages."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    # Only counted when a page actually shows the nav.
    return {"unread_message_count": SimpleLazyObject(lambda: unread_count(user))}
