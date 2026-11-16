"""How a forum author is shown: their name and avatar color, the same as in
Messages ("Chloe Shih" for caregivers, "Kat W." for pet owners), and whether
they are a pet owner or a caregiver, like the rest of PawPal."""

from messaging.inbox import person


def initials(user):
    if not user.is_active:
        return "?"
    if user.first_name and user.last_name:
        return (user.first_name[0] + user.last_name[0]).upper()
    return (user.first_name or user.username)[:2].upper()


def display_name(user):
    """The name on posts and comments, as in Messages and the Figma."""
    if not user.is_active:
        return "Deleted account"
    return person(user)["name"]


def theme(user):
    """The avatar color the person has in Messages ("blue", "mint", ...)."""
    if not user.is_active:
        return "deleted"
    return person(user)["theme"]


def role(user):
    if user.is_staff:
        return "Admin"
    profile = getattr(user, "account_profile", None)
    if getattr(user, "caregiver_profile", None) is not None or (
        profile is not None and profile.role == "caregiver"
    ):
        return "Caregiver"
    return "Pet owner"


def describe(item):
    """Add author_name, author_initials, author_theme and author_role to a
    post or comment for the templates. Everyone, you included, has the same
    color as in Messages, whoever is looking."""
    item.author_name = display_name(item.author)
    item.author_initials = initials(item.author)
    item.author_theme = theme(item.author)
    item.author_role = role(item.author)
    return item
