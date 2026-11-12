"""How a forum author is shown: a short name ("Kat W.") and whether they are a
pet owner or a caregiver, like the rest of PawPal."""


def short_name(user):
    if not user.is_active:
        return "Deleted account"
    if user.first_name:
        initial = f" {user.last_name[0].upper()}." if user.last_name else ""
        return f"{user.first_name}{initial}"
    return user.username


def initials(user):
    if not user.is_active:
        return "?"
    if user.first_name and user.last_name:
        return (user.first_name[0] + user.last_name[0]).upper()
    return (user.first_name or user.username)[:2].upper()


def role(user):
    if user.is_staff:
        return "Admin"
    profile = getattr(user, "account_profile", None)
    if getattr(user, "caregiver_profile", None) is not None or (
        profile is not None and profile.role == "caregiver"
    ):
        return "Caregiver"
    return "Pet owner"


def describe(post):
    """Add author_name, author_initials and author_role for the templates."""
    post.author_name = short_name(post.author)
    post.author_initials = initials(post.author)
    post.author_role = role(post.author)
    return post
