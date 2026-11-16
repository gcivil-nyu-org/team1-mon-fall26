"""Dog fountains from NYC Parks: drinking fountains with a bowl for dogs.
NYC Parks' rules say dogs may drink only from these
(https://www.nycgovparks.org/facilities/dogareas).

Dataset qnv7-p7a2 (https://data.cityofnewyork.us/d/qnv7-p7a2) lists every
outdoor drinking fountain in NYC parks. Each row has an id ("system"), its type
("fountainty", e.g. "E and Dog" when it has a dog bowl), the park
("propertyna"), a description ending with the area of the park, where it
stands ("position", e.g. "Under Tree, In Shade"), its status and a point.
"""

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from .nyc_open_data import NYC_BOUNDS

DATASET_ID = "qnv7-p7a2"
DATASET_URL = f"https://data.cityofnewyork.us/d/{DATASET_ID}"
API_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json?" + urlencode(
    {"$where": "fountainty like '%Dog%'", "$limit": "5000"}
)

BOROUGHS = {
    "X": "Bronx",
    "B": "Brooklyn",
    "M": "Manhattan",
    "Q": "Queens",
    "R": "Staten Island",
}
FEATURE = "Water bowl for dogs"


def _text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def _coordinate(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _area(row):
    """ "E and Dog-Central Park-Cedar Hill" -> "Cedar Hill" (or "")."""
    parts = _text(row.get("decription")).split("-")
    return parts[2].strip() if len(parts) > 2 else ""


def dog_fountains(rows):
    """One place per working dog fountain. Fountains without a dog bowl, not
    active, inside a playground (dogs aren't allowed there), without a point
    or outside NYC are left out."""
    (south, north), (west, east) = NYC_BOUNDS
    places = []
    for row in rows:
        if "dog" not in (row.get("fountainty") or "").lower():
            continue
        if (row.get("featuresta") or "").strip().lower() != "active":
            continue
        position = _text(row.get("position"))
        if re.search(r"(^|,\s*)in playground", position, re.I):
            continue
        coords = ((row.get("the_geom") or {}).get("coordinates") or [None, None])[:2]
        longitude, latitude = (_coordinate(c) for c in coords)
        if latitude is None or longitude is None:
            continue
        if not (south <= latitude <= north and west <= longitude <= east):
            continue
        park = _text(row.get("propertyna"))
        area = _area(row)
        name = f"Dog fountain, {park}" if park else "Dog fountain"
        if area and area.lower() != park.lower():
            name = f"{name} ({area})"
        features = [FEATURE]
        if position:
            features.append(position[:1].upper() + position[1:].lower())
        places.append(
            {
                "source_id": _text(row.get("system"))[:64],
                "name": name[:150],
                "neighborhood": park[:100],
                "borough": BOROUGHS.get((row.get("borough") or "")[:1].upper(), ""),
                "latitude": latitude,
                "longitude": longitude,
                "features": "\n".join(features),
            }
        )
    return sorted(
        (p for p in places if p["source_id"]),
        key=lambda p: (p["name"], p["source_id"]),
    )
