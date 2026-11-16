"""Outdoor dining from NYC Open Data: NYC DOT's "Dining Out NYC" licenses.

Dataset fpeh-f7ci (https://data.cityofnewyork.us/d/fpeh-f7ci) lists every
restaurant and café licensed for sidewalk or roadway seating. Each row is one
license: the business's legal name and the name it trades under
("assumed_name_s"), street, borough, ZIP code, license type ("Sidewalk" or
"Roadway"), license status and coordinates. A place with both kinds of seating
has two rows.

NYC's Health Code lets each restaurant choose whether pet dogs may sit in its
outdoor area, so PawPal shows these as places to ask, not as pet-friendly.
"""

import hashlib
import re
from decimal import Decimal, InvalidOperation

from .nyc_open_data import NYC_BOUNDS

DATASET_ID = "fpeh-f7ci"
DATASET_URL = f"https://data.cityofnewyork.us/d/{DATASET_ID}"
# Only licenses in force; one request is enough for the whole city.
API_URL = (
    f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
    "?license_status=Issued&$limit=50000"
)

BOROUGHS = {"Manhattan", "Brooklyn", "Bronx", "Queens", "Staten Island"}


def tidy(text):
    """ "BURGERFI" -> "Burgerfi", "719 86 STREET" -> "719 86 Street".
    Text that already has lower-case letters is kept as typed."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if text != text.upper():
        return text
    return " ".join(
        word if any(c.isdigit() for c in word) else word.capitalize()
        for word in text.lower().split(" ")
    )


def _coordinate(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _borough(value):
    value = tidy(value or "")
    if value == "The Bronx":
        return "Bronx"
    return value if value in BOROUGHS else ""


def outdoor_dining(rows):
    """One place per business and street from the license rows: name, address,
    borough, ZIP code, coordinates, its seating as features and a source id
    that stays the same between imports. Rows outside the five boroughs,
    without a name or coordinates, or not Issued are left out."""
    places = {}
    for row in rows:
        if (row.get("license_status") or "").strip().lower() != "issued":
            continue
        borough = _borough(row.get("borough"))
        name = tidy(row.get("assumed_name_s") or row.get("business_legal_name"))
        street = tidy(row.get("street"))
        latitude = _coordinate(row.get("latitude"))
        longitude = _coordinate(row.get("longitude"))
        if not (borough and name and latitude and longitude):
            continue
        (south, north), (west, east) = NYC_BOUNDS
        if not (south <= latitude <= north and west <= longitude <= east):
            continue
        key = f"{name.lower()}|{street.lower()}|{borough.lower()}"
        place = places.get(key)
        if place is None:
            place = places[key] = {
                "source_id": hashlib.sha1(key.encode()).hexdigest()[:16],
                "name": name[:150],
                "address": street[:200],
                "borough": borough,
                "zip_code": (row.get("postcode") or "").strip()[:20],
                "latitude": latitude,
                "longitude": longitude,
                "seating": set(),
            }
        seating = tidy(row.get("license_type"))
        if seating:
            place["seating"].add(seating)
    result = []
    for place in places.values():
        seating = sorted(place.pop("seating"))
        lines = [f"{kind} seating" for kind in seating] or ["Outdoor seating"]
        place["features"] = "\n".join(lines)
        result.append(place)
    return sorted(result, key=lambda p: (p["name"], p["source_id"]))
