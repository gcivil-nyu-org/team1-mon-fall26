"""Dog-friendly cafés and restaurants from Google Maps (Places API).

NYC Open Data has no list of pet-friendly businesses, and OpenStreetMap marks
only a few dozen New York cafés and restaurants as dog-friendly. Google Maps
records "Allows dogs" for many more, so when someone searches Explore for
cafés or restaurants near a place, PawPal asks the Places API (New) Text
Search for dog-friendly ones there and keeps those Google says allow dogs.

Google's terms allow keeping a place's id and only caching the rest for a
short time, so these places are refreshed by later searches and deleted once
they haven't been checked for CACHE_DAYS days. Without GOOGLE_PLACES_API_KEY
(local development, tests) nothing is asked and Explore works as before.

Pricing: asking for allowsDogs puts each search in the "Text Search
Enterprise + Atmosphere" SKU, which has 1,000 free calls a month. A search
costs one call per category, and the same area isn't asked again for
SEARCH_AGAIN_AFTER seconds.
"""

import json
import logging
from datetime import timedelta
from decimal import Decimal
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from caregivers.search import nearest_neighborhood

from .models import Place
from .nyc_open_data import NYC_BOUNDS

logger = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TIMEOUT_SECONDS = 10
# Text Search returns at most 20 places per call; we only ask for one page.
PAGE_SIZE = 20
FIELD_MASK = ",".join(
    "places." + field
    for field in (
        "id",
        "displayName",
        "location",
        "addressComponents",
        "primaryType",
        "allowsDogs",
        "outdoorSeating",
        "regularOpeningHours",
    )
)
# The same area and category is asked again after a day at the earliest.
SEARCH_AGAIN_AFTER = 60 * 60 * 24
# Places not refreshed by a search for this long are deleted.
CACHE_DAYS = 30
MILES_TO_DEGREES_LAT = 1 / 69.0
MILES_TO_DEGREES_LNG = 1 / 52.0

# The categories Google is asked about, and what each search asks for.
SEARCHES = {
    Place.Category.CAFE: ("dog friendly cafe", "cafe"),
    Place.Category.RESTAURANT: ("dog friendly restaurant", "restaurant"),
}
# Google place types shown as cafés; everything else found is a restaurant.
CAFE_TYPES = {
    "cafe",
    "coffee_shop",
    "bakery",
    "ice_cream_shop",
    "tea_house",
    "dessert_shop",
    "juice_shop",
    "cat_cafe",
    "dog_cafe",
}

FIELDS = (
    "name",
    "category",
    "address",
    "zip_code",
    "neighborhood",
    "borough",
    "latitude",
    "longitude",
    "weekly_hours",
    "features",
)


class GooglePlacesUnavailable(Exception):
    pass


def enabled():
    return bool(getattr(settings, "GOOGLE_PLACES_API_KEY", ""))


def _rectangle(latitude, longitude, miles):
    lat, lng = miles * MILES_TO_DEGREES_LAT, miles * MILES_TO_DEGREES_LNG
    return {
        "low": {"latitude": latitude - lat, "longitude": longitude - lng},
        "high": {"latitude": latitude + lat, "longitude": longitude + lng},
    }


def search(text, place_type, latitude, longitude, miles):
    """Places API Text Search within `miles` of the point, as JSON.
    Raises GooglePlacesUnavailable."""
    body = {
        "textQuery": text,
        "includedType": place_type,
        "pageSize": PAGE_SIZE,
        "locationRestriction": {
            "rectangle": _rectangle(float(latitude), float(longitude), miles)
        },
    }
    request = Request(
        SEARCH_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as error:
        raise GooglePlacesUnavailable(str(error)) from error


def weekly_hours(opening_hours):
    """Google regularOpeningHours -> the 7 days PawPal stores (Monday first,
    each {"open", "close"} or None when closed). Days with more than one
    opening (a lunch break) or places open around the clock give [], so no
    hours are shown rather than wrong ones."""
    periods = (opening_hours or {}).get("periods") or []
    if not periods:
        return []
    week = [None] * 7
    for period in periods:
        opens, closes = period.get("open"), period.get("close")
        if not opens or not closes:
            # Open 24 hours: Google sends an opening with no closing.
            return []
        # Google counts days from Sunday (0); PawPal from Monday.
        day = (opens.get("day", 0) - 1) % 7
        if week[day] is not None:
            return []
        week[day] = {
            "open": f"{opens.get('hour', 0):02d}:{opens.get('minute', 0):02d}",
            "close": f"{closes.get('hour', 0):02d}:{closes.get('minute', 0):02d}",
        }
        if week[day]["open"] == week[day]["close"]:
            return []
    return week


def _component(components, kind):
    for component in components:
        if kind in component.get("types", []):
            return (
                component.get("shortText") or component.get("longText") or ""
            ).strip()
    return ""


def _address(components):
    number = _component(components, "street_number")
    street = _component(components, "route")
    return f"{number} {street}".strip() if street else ""


def google_places(data):
    """One place per result Google says allows dogs: its id, name, category,
    address, ZIP code, neighborhood and borough (from the nearest NYC
    neighborhood), coordinates, day-by-day hours where they can be read and
    features. Also returns the ids of results Google says don't allow dogs.
    Results without a name or coordinates, or outside New York City, are
    left out."""
    places, no_dogs = [], []
    for result in (data or {}).get("places", []):
        place_id = (result.get("id") or "")[:64]
        if not place_id:
            continue
        if result.get("allowsDogs") is False:
            no_dogs.append(place_id)
            continue
        if result.get("allowsDogs") is not True:
            # Google doesn't know: not shown as dog-friendly.
            continue
        name = " ".join(((result.get("displayName") or {}).get("text") or "").split())
        location = result.get("location") or {}
        try:
            latitude = Decimal(str(location["latitude"])).quantize(Decimal("0.000001"))
            longitude = Decimal(str(location["longitude"])).quantize(
                Decimal("0.000001")
            )
        except (KeyError, ArithmeticError, ValueError):
            continue
        (south, north), (west, east) = NYC_BOUNDS
        if not name or not (south <= latitude <= north and west <= longitude <= east):
            continue
        components = result.get("addressComponents") or []
        area = nearest_neighborhood(float(latitude), float(longitude))
        features = ["Dogs welcome"]
        if result.get("outdoorSeating"):
            features.append("Outdoor seating")
        places.append(
            {
                "source_id": place_id,
                "name": name[:150],
                "category": (
                    Place.Category.CAFE
                    if result.get("primaryType") in CAFE_TYPES
                    else Place.Category.RESTAURANT
                ),
                "address": _address(components)[:200],
                "zip_code": _component(components, "postal_code")[:5],
                "neighborhood": area["name"][:100],
                "borough": area["borough"][:20],
                "latitude": latitude,
                "longitude": longitude,
                "weekly_hours": weekly_hours(result.get("regularOpeningHours")),
                "features": "\n".join(features),
            }
        )
    return places, no_dogs


@transaction.atomic
def update_google_places(rows, no_dogs, checked_on):
    """Add or refresh the places found and hide those Google now says don't
    allow dogs. Places an admin edited are left as the admin set them.
    Returns (added, updated, hidden)."""
    ids = [row["source_id"] for row in rows] + list(no_dogs)
    existing = {
        p.source_id: p
        for p in Place.objects.filter(source=Place.Source.GOOGLE, source_id__in=ids)
    }
    added = updated = 0
    for row in rows:
        place = existing.get(row["source_id"])
        if place is not None and place.edited_at is not None:
            continue
        if place is None:
            place = Place(source=Place.Source.GOOGLE, source_id=row["source_id"])
            added += 1
        else:
            updated += 1
        for field in FIELDS:
            setattr(place, field, row[field])
        place.checked_on = checked_on
        place.is_active = True
        place.save()
    hidden = Place.objects.filter(
        source=Place.Source.GOOGLE,
        source_id__in=no_dogs,
        is_active=True,
        edited_at=None,
    ).update(is_active=False)
    return added, updated, hidden


def delete_old_places(today=None):
    """Delete Google places no search has refreshed for CACHE_DAYS days
    (unless an admin edited them). Returns how many were deleted."""
    today = today or timezone.localdate()
    deleted, _ = Place.objects.filter(
        source=Place.Source.GOOGLE,
        checked_on__lt=today - timedelta(days=CACHE_DAYS),
        edited_at=None,
    ).delete()
    return deleted


def _cache_key(category, latitude, longitude, miles):
    # About a kilometer apart counts as the same area.
    return (
        f"google-places:{category}:{round(float(latitude), 2)}:"
        f"{round(float(longitude), 2)}:{miles}"
    )


def refresh_near(latitude, longitude, miles, category=""):
    """Before Explore lists places near a point, ask Google for dog-friendly
    cafés and/or restaurants there (only the category asked for, or both
    under "All"). Does nothing without an API key, for other categories, or
    when the same area was asked recently. Problems are logged, never shown:
    Explore still lists the places it already has."""
    if not enabled():
        return
    if category and category not in SEARCHES:
        return
    delete_old_places()
    categories = [category] if category else list(SEARCHES)
    for wanted in categories:
        key = _cache_key(wanted, latitude, longitude, miles)
        if cache.get(key):
            continue
        text, place_type = SEARCHES[wanted]
        try:
            data = search(text, place_type, latitude, longitude, miles)
        except GooglePlacesUnavailable as error:
            logger.warning("Google Places search failed: %s", error)
            continue
        rows, no_dogs = google_places(data)
        update_google_places(rows, no_dogs, timezone.localdate())
        cache.set(key, True, SEARCH_AGAIN_AFTER)
