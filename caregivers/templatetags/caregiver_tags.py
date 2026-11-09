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
    # The first profile gets the first color, as in the design (orange, blue, ...).
    return AVATAR_THEMES[((caregiver.pk or 1) - 1) % len(AVATAR_THEMES)]


# Pet tags as the design shows them: plural, the most common pets first.
PET_ORDER = ("Dog", "Cat", "Rabbit", "Bird")
PET_PLURALS = {"Fish": "Fish", "Mouse": "Mice", "Other": "Other pets"}


def pet_plural(name):
    """ "Dog" -> "Dogs", "Guinea pig" -> "Guinea pigs", "Mouse" -> "Mice"."""
    if name in PET_PLURALS:
        return PET_PLURALS[name]
    if name.endswith(("s", "x", "ch", "sh")):
        return name + "es"
    return name + "s"


@register.filter
def pet_tags(pet_types):
    """Pet type names for a caregiver card: ["Dogs", "Cats", "Rabbits"]."""
    names = [p.name for p in pet_types]
    order = {name: i for i, name in enumerate(PET_ORDER)}
    names.sort(key=lambda n: (order.get(n, len(PET_ORDER)), n.lower()))
    return [pet_plural(n) for n in names]


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
