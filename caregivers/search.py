"""Finding caregivers near a place in New York City (story #33) and filtering
them by service (#34) and availability (#35)."""

import json
import re
from functools import lru_cache
from pathlib import Path

from django.db.models import Exists, OuterRef, Prefetch, Q

from .geocoding import distance_miles
from .models import CaregiverProfile, CaregiverService, ServiceType

DATA_DIR = Path(__file__).resolve().parent / "data"
NEIGHBORHOODS_FILE = DATA_DIR / "nyc_neighborhoods.json"
ZIP_CODES_FILE = DATA_DIR / "nyc_zip_codes.json"

# How far owners can ask to search, in miles (the Distance menu).
DISTANCE_CHOICES = (1, 2, 5, 10)
DEFAULT_DISTANCE = 5
# How much farther than the chosen distance "nearby" suggestions can be.
NEARBY_EXTRA_MILES = 4

# Ways to order results (the sort menu); "closest" needs a location.
SORT_CHOICES = {
    "closest": "Closest first",
    "experience": "Most experienced",
    "name": "Name (A-Z)",
}

# The largest service radius a caregiver can set (see CaregiverProfile).
MAX_RADIUS_MILES = 25
# Degrees of latitude / longitude that cover MAX_RADIUS_MILES around NYC,
# used to narrow the database query before measuring exact distances.
LAT_DEGREES = MAX_RADIUS_MILES / 69.0
LNG_DEGREES = MAX_RADIUS_MILES / 52.0


@lru_cache(maxsize=1)
def neighborhoods():
    """NYC neighborhoods with a center point, sorted by borough and name."""
    with NEIGHBORHOODS_FILE.open() as f:
        return json.load(f)["neighborhoods"]


def neighborhood(code):
    """The neighborhood with this NTA code (e.g. "MN0202"), or None."""
    return next((n for n in neighborhoods() if n["code"] == code), None)


@lru_cache(maxsize=1)
def zip_codes():
    """NYC ZIP codes with a center point and the nearest neighborhood."""
    with ZIP_CODES_FILE.open() as f:
        return json.load(f)["zip_codes"]


def _simplify(text):
    return " ".join(text.lower().replace("\u2019", "'").split())


def find_neighborhood(text):
    """The neighborhood the owner typed, e.g. "Park Slope" or "Astoria, Queens".

    Matches the full name, or one part of a combined name such as
    "Windsor Terrace-South Slope" or "Astoria (Central)". Returns None if
    nothing matches.
    """
    name, _, borough = _simplify(text).partition(",")
    name, borough = name.strip(), borough.strip()
    if not name:
        return None
    candidates = [
        n for n in neighborhoods() if not borough or _simplify(n["borough"]) == borough
    ]
    for n in candidates:
        if _simplify(n["name"]) == name:
            return n
    for n in candidates:
        if name in _name_parts(n["name"]):
            return n
    # "Astoria" for "Astoria (Central)".
    for n in candidates:
        if name in (re.sub(r"\s*\(.*?\)", "", part) for part in _name_parts(n["name"])):
            return n
    return None


def _name_parts(name):
    return [part.strip() for part in _simplify(name).split("-")]


def find_zip_code(text):
    """The place for an NYC ZIP code like "11215", or None."""
    code = text.strip()
    place = zip_codes().get(code) if code.isdigit() and len(code) == 5 else None
    if place is None:
        return None
    return {
        "label": f"{code} ({place['neighborhood']})",
        "latitude": place["latitude"],
        "longitude": place["longitude"],
    }


def nearest_neighborhood(latitude, longitude):
    """The neighborhood whose center is closest to the point."""
    return min(
        neighborhoods(),
        key=lambda n: distance_miles(
            latitude, longitude, n["latitude"], n["longitude"]
        ),
    )


def listed_services():
    """Services a caregiver offers (active). A price is optional."""
    return CaregiverService.objects.filter(is_active=True)


def searchable_caregivers(viewer, available_only=True):
    """Caregivers with an account, with what the cards show.

    By default only caregivers taking new bookings are included (#35); with
    available_only=False the others are listed too, but can't be requested.
    """
    # Only caregivers with an active account (deleted accounts are deactivated, #48).
    caregivers = CaregiverProfile.objects.filter(
        user__isnull=False, user__is_active=True
    )
    if available_only:
        caregivers = caregivers.filter(accepting_new_bookings=True)
    caregivers = caregivers.prefetch_related(
        "supported_pet_types",
        Prefetch(
            "caregiverservice_set",
            queryset=listed_services()
            .select_related("service_type")
            .order_by("service_type__name"),
            to_attr="listed_services",
        ),
    ).order_by("name")
    if viewer.is_authenticated:
        caregivers = caregivers.exclude(user=viewer)
    return caregivers


def caregivers_near(caregivers, latitude, longitude, max_miles=None):
    """Caregivers whose service radius covers the point, nearest first.

    With max_miles, caregivers farther away than that are left out too, so
    both the owner's Distance and the caregiver's own radius have to fit.
    Each returned caregiver gets a `distance` attribute in miles.
    """
    latitude, longitude = float(latitude), float(longitude)
    nearby = caregivers.filter(
        latitude__range=(latitude - LAT_DEGREES, latitude + LAT_DEGREES),
        longitude__range=(longitude - LNG_DEGREES, longitude + LNG_DEGREES),
    )
    results = []
    for caregiver in nearby:
        caregiver.distance = distance_miles(
            latitude, longitude, caregiver.latitude, caregiver.longitude
        )
        limit = caregiver.service_radius_miles
        if max_miles is not None:
            limit = min(limit, max_miles)
        if caregiver.distance <= limit:
            results.append(caregiver)
    results.sort(key=lambda c: (c.distance, c.name))
    return results


def caregivers_matching_text(caregivers, text):
    """Fallback when the address lookup is down: match the area by name."""
    return list(
        caregivers.filter(
            Q(neighborhood__icontains=text) | Q(service_area__icontains=text)
        )
    )


def offered_service_types():
    """Service types at least one caregiver lists, for the service filter (#34)."""
    offered = listed_services().filter(
        service_type=OuterRef("pk"), caregiver__user__is_active=True
    )
    return ServiceType.objects.filter(Exists(offered)).order_by("name")


def offering_service(caregivers, service_type):
    """Caregivers who offer this service (#34)."""
    offers = listed_services().filter(
        caregiver=OuterRef("pk"), service_type=service_type
    )
    return caregivers.filter(Exists(offers))


def put_service_first(caregivers, service_type):
    """Show the filtered service first on each card."""
    for caregiver in caregivers:
        caregiver.listed_services.sort(
            key=lambda s: s.service_type_id != service_type.pk
        )
    return caregivers


def sort_caregivers(caregivers, sort, has_origin):
    """Order results by the owner's choice; "closest" only works with a location."""
    if sort == "experience":
        return sorted(caregivers, key=lambda c: (-c.years_of_experience, c.name))
    if sort == "closest" and has_origin:
        return caregivers  # caregivers_near already sorts nearest first
    return sorted(caregivers, key=lambda c: c.name)


def nearby_suggestions(caregivers, latitude, longitude, max_miles, limit=3):
    """Up to `limit` neighborhoods near the point where a search would find someone.

    Shown when a search has no results. `caregivers` is the filtered queryset.
    """
    pool = [c for c in caregivers if c.latitude is not None and c.longitude is not None]
    if not pool:
        return []
    # Only neighborhoods a short trip away count as "nearby".
    reach = max_miles + NEARBY_EXTRA_MILES
    nearby = []
    for hood in neighborhoods():
        miles = distance_miles(latitude, longitude, hood["latitude"], hood["longitude"])
        if miles <= reach:
            nearby.append((miles, hood))
    nearby.sort(key=lambda pair: pair[0])
    suggestions = []
    for _, hood in nearby:
        served = any(
            distance_miles(hood["latitude"], hood["longitude"], c.latitude, c.longitude)
            <= min(c.service_radius_miles, max_miles)
            for c in pool
        )
        if served:
            suggestions.append(hood)
            if len(suggestions) == limit:
                break
    return suggestions
