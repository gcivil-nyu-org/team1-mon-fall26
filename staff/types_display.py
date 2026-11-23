"""How the Pet & service types page (Kat's Figma "Admin (Pet & Service
Types)") draws each type's round avatar: every type gets one of Figma's six
colors, so no avatar is left plain."""

from zlib import crc32

# Figma's avatar colors, in the order the page uses them.
COLORS = ("peach", "green", "pink", "yellow", "blue", "purple")

# The pet types Figma shows keep their Figma colors.
PET_COLORS = {
    "dog": "peach",
    "cat": "green",
    "rabbit": "pink",
    "bunny": "pink",
    "bird": "yellow",
}

# Each service icon has its Figma color.
SERVICE_COLORS = {
    "walk": "peach",
    "home": "blue",
    "night": "purple",
    "feeding": "mint",  # Figma's lighter green for Feeding & medication
}


def name_color(name):
    """The same color for the same name every time, for types Figma doesn't
    show (like one an admin just added)."""
    return COLORS[crc32(name.strip().lower().encode()) % len(COLORS)]


def pet_color(pet_type):
    return PET_COLORS.get(pet_type.name.strip().lower()) or name_color(pet_type.name)


def service_kind(service_type):
    """Which icon the service gets, as in Figma "Manage Service Types": a paw
    for walks, a house for drop-ins, a moon for overnight stays, a bowl for
    feeding. Anything else gets a paw too ("other")."""
    name = service_type.name.lower()
    if any(word in name for word in ("walk", "daycare", "training")):
        return "walk"
    if "drop-in" in name or "drop in" in name or "visit" in name:
        return "home"
    if any(word in name for word in ("overnight", "sitting", "boarding")):
        return "night"
    if any(word in name for word in ("feeding", "medication")):
        return "feeding"
    return "other"


def service_color(service_type, kind):
    return SERVICE_COLORS.get(kind) or name_color(service_type.name)
