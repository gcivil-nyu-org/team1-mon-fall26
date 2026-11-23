"""Pet stores and dog-friendly cafés and restaurants from OpenStreetMap.

NYC Open Data has no list of pet-friendly businesses, so these come from
OpenStreetMap (https://www.openstreetmap.org), the open map that the Explore
map's streets already come from. Its data is free to use under the Open
Database License, crediting "© OpenStreetMap contributors".

The Overpass API (https://overpass-api.de) answers one query for all of New
York City (the area with Wikidata id Q60):
- pet stores: shop=pet;
- cafés, restaurants, bars and the like whose mappers recorded that dogs are
  allowed: dog=yes (inside), dog=leashed, dog=outside or dog=designated.
Each result has its name, coordinates (the center, for a building outline) and
tags such as addr:housenumber, addr:street, addr:postcode, outdoor_seating and
opening_hours.
"""

import json
import re
from decimal import Decimal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from caregivers.search import nearest_neighborhood

from .nyc_open_data import NYC_BOUNDS, OpenDataUnavailable

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
TIMEOUT_SECONDS = 60
DOG_VALUES = "yes|leashed|outside|designated"
CAFES = {"cafe", "ice_cream"}
RESTAURANTS = {"restaurant", "bar", "pub", "fast_food", "biergarten"}
QUERY = f"""[out:json][timeout:{TIMEOUT_SECONDS}];
area["wikidata"="Q60"]->.nyc;
(
  nwr["shop"="pet"]["name"](area.nyc);
  nwr["amenity"~"^({'|'.join(sorted(CAFES | RESTAURANTS))})$"]["dog"~"^({DOG_VALUES})$"]["name"](area.nyc);
);
out center tags;"""

# What each "dog" value means, as a line on the place's card.
DOGS = {
    "yes": "Dogs welcome inside",
    "designated": "Dogs welcome inside",
    "leashed": "Leashed dogs welcome",
    "outside": "Dogs welcome outside",
}

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def download(query=QUERY):
    """The Overpass API's answer, as JSON. Raises OpenDataUnavailable."""
    request = Request(
        OVERPASS_URL,
        data=urlencode({"data": query}).encode(),
        headers={"User-Agent": "PawPal (NYU course project)"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS + 30) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as error:
        raise OpenDataUnavailable(str(error)) from error


def _days(selector):
    """ "Mo-Fr" -> [0, 1, 2, 3, 4], "Sa,Su" -> [5, 6]; None if not understood."""
    days = []
    for part in selector.split(","):
        if "-" in part:
            first, _, last = part.partition("-")
            if first not in DAYS or last not in DAYS:
                return None
            start, end = DAYS.index(first), DAYS.index(last)
            days += [d % 7 for d in range(start, end + 1 if end >= start else end + 8)]
        elif part in DAYS:
            days.append(DAYS.index(part))
        else:
            return None
    return days


def _clock(hours, minutes):
    hours, minutes = int(hours), int(minutes)
    if hours == 24 and minutes == 0:
        # Closes at midnight: the next day's 00:00 (hours past midnight work).
        return "00:00"
    if hours > 23 or minutes > 59:
        return None
    return f"{hours:02d}:{minutes:02d}"


def weekly_hours(text):
    """OpenStreetMap opening_hours -> the 7 days PawPal stores (Monday first,
    each {"open", "close"} or None when closed). Only the common simple forms
    are read ("Mo-Fr 08:00-18:00; Sa,Su 09:00-17:00", "Mo off"); anything more
    involved (lunch breaks, months, holidays, "24/7") gives [], so no hours are
    shown rather than wrong ones."""
    week = [None] * 7
    rules = [rule.strip() for rule in (text or "").split(";") if rule.strip()]
    if not rules:
        return []
    for rule in rules:
        parts = rule.split()
        if parts[0].startswith(("PH", "SH")):
            # Public and school holidays: not shown.
            continue
        if len(parts) == 1 and TIME_RANGE.match(parts[0]):
            # Times alone: every day.
            parts = ["Mo-Su", parts[0]]
        if len(parts) != 2:
            return []
        days = _days(parts[0])
        if days is None:
            return []
        if parts[1] in {"off", "closed"}:
            hours = None
        else:
            match = TIME_RANGE.match(parts[1])
            if not match:
                return []
            opens, closes = _clock(*match.groups()[:2]), _clock(*match.groups()[2:])
            if opens is None or closes is None or opens == closes:
                return []
            hours = {"open": opens, "close": closes}
        for day in days:
            week[day] = hours
    return week if any(week) else []


def _address(tags):
    number = (tags.get("addr:housenumber") or "").strip()
    street = (tags.get("addr:street") or "").strip()
    return f"{number} {street}".strip() if street else ""


def _category(tags):
    if tags.get("shop") == "pet":
        return "pet_store"
    if tags.get("amenity") in CAFES:
        return "cafe"
    return "restaurant"


def _features(tags, category):
    lines = []
    dog = DOGS.get((tags.get("dog") or "").strip().lower())
    if dog:
        lines.append(dog)
    elif category == "pet_store":
        lines.append("Pet food and supplies")
    if (tags.get("outdoor_seating") or "").lower() == "yes":
        lines.append("Outdoor seating")
    return lines


def osm_places(data):
    """One place per OpenStreetMap result: name, category, address, ZIP code,
    neighborhood and borough (from the nearest NYC neighborhood), coordinates,
    day-by-day hours where they can be read, features and a source id such as
    "node/123" that stays the same between imports. Results without a name or
    coordinates, or outside New York City, are left out."""
    places = []
    for element in (data or {}).get("elements", []):
        tags = element.get("tags") or {}
        name = " ".join((tags.get("name") or "").split())
        point = element.get("center") or element
        try:
            latitude = Decimal(str(point["lat"])).quantize(Decimal("0.000001"))
            longitude = Decimal(str(point["lon"])).quantize(Decimal("0.000001"))
        except (KeyError, ArithmeticError, ValueError):
            continue
        (south, north), (west, east) = NYC_BOUNDS
        if not name or not (south <= latitude <= north and west <= longitude <= east):
            continue
        category = _category(tags)
        area = nearest_neighborhood(float(latitude), float(longitude))
        places.append(
            {
                "source_id": f"{element.get('type', 'node')}/{element.get('id')}"[:64],
                "name": name[:150],
                "category": category,
                "address": _address(tags)[:200],
                "zip_code": (tags.get("addr:postcode") or "").strip()[:5],
                "neighborhood": area["name"][:100],
                "borough": area["borough"][:20],
                "latitude": latitude,
                "longitude": longitude,
                "weekly_hours": weekly_hours(tags.get("opening_hours")),
                "features": "\n".join(_features(tags, category)),
            }
        )
    return sorted(places, key=lambda p: (p["name"].lower(), p["source_id"]))
