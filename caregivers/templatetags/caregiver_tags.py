"""Small display helpers for caregiver cards (Find caregivers page)."""

from django import template

register = template.Library()

# Avatar colors from the Figma design, picked by profile id.
AVATAR_THEMES = ("peach", "blue", "mint", "pink")


@register.filter
def initials(name):
    """ "Chloe Shih" -> "CS", "Madonna" -> "M"."""
    words = [w for w in (name or "").split() if w[:1].isalpha()]
    if not words:
        return "?"
    letters = words[0][0] + (words[-1][0] if len(words) > 1 else "")
    return letters.upper()


@register.filter
def place_name(label):
    """ "Park Slope, Brooklyn" -> "Park Slope" for the results heading, like the design."""
    return str(label).split(",")[0].strip()


@register.filter
def avatar_theme(caregiver):
    return AVATAR_THEMES[(caregiver.pk or 0) % len(AVATAR_THEMES)]


@register.filter
def experience_range(years):
    """Years of experience as the ranges the design shows."""
    years = years or 0
    if years < 1:
        return "Under 1 year"
    if years <= 2:
        return "1–2 years"
    if years <= 5:
        return "3–5 years"
    return "5+ years"
