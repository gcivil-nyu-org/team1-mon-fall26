"""Finding pet-friendly places near where the owner is searching from.

Where they search from works the same as on the caregiver search: a
neighborhood, a ZIP code, a street address (NYC GeoSearch), a suggestion picked
in the browser, or their current location.
"""

from caregivers.geocoding import GeocodingUnavailable, distance_miles, geocode
from caregivers.search import nearest_neighborhood
from caregivers.views import _coordinates, _place_for

from .models import Place

# Degrees around the origin worth checking before measuring exact distances
# (a little more than the largest Distance choice, 10 miles).
LAT_DEGREES = 11 / 69.0
LNG_DEGREES = 11 / 52.0

# What the chips and headings call each category: (one, many).
NAMES = {
    "": ("place", "places"),
    Place.Category.DOG_PARK: ("dog park", "dog parks"),
    Place.Category.CAFE: ("café", "cafés"),
    Place.Category.PET_STORE: ("pet store", "pet stores"),
    Place.Category.RESTAURANT: ("restaurant", "restaurants"),
}


def find_origin(params):
    """Where the owner is searching from, as ({"label", "latitude",
    "longitude"} or None, notice)."""
    text = (params.get("location") or "").strip()
    latitude, longitude = _coordinates(params)
    if params.get("here") == "1":
        if latitude is None:
            return None, (
                "Your current location isn't in New York City. "
                "Enter a neighborhood or ZIP code instead."
            )
        hood = nearest_neighborhood(latitude, longitude)
        label = f"you ({hood['name']})"
        return {"label": label, "latitude": latitude, "longitude": longitude}, ""
    if not text:
        return None, ""
    if latitude is not None:
        # Picked from the suggestions in the browser.
        return {"label": text, "latitude": latitude, "longitude": longitude}, ""
    place = _place_for(text)
    if place is not None:
        return place, ""
    try:
        location = geocode(text)
    except GeocodingUnavailable:
        return None, (
            "Address search is unavailable right now. "
            "Try a neighborhood or ZIP code."
        )
    if location is None:
        return None, (
            "We couldn't find that place in New York City. "
            "Try a neighborhood, ZIP code or street address."
        )
    return {
        "label": text,
        "latitude": location.latitude,
        "longitude": location.longitude,
    }, ""


def places_near(places, latitude, longitude, max_miles):
    """Places within max_miles of the point, nearest first, each with a
    `distance` in miles."""
    latitude, longitude = float(latitude), float(longitude)
    nearby = places.filter(
        latitude__range=(latitude - LAT_DEGREES, latitude + LAT_DEGREES),
        longitude__range=(longitude - LNG_DEGREES, longitude + LNG_DEGREES),
    )
    results = []
    for place in nearby:
        place.distance = distance_miles(
            latitude, longitude, place.latitude, place.longitude
        )
        if place.distance <= max_miles:
            results.append(place)
    results.sort(key=lambda p: (p.distance, p.name))
    return results
