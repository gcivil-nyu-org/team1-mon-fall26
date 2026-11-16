"""Off-leash areas from NYC Parks: parks where dogs may be off leash before
9 AM and after 9 PM (a few only 6-9 AM), as listed on NYC Parks' "Dog-friendly
Areas" page (https://www.nycgovparks.org/facilities/dogareas).

The list comes from NYC Parks' dog areas directory (NYC Open Data ipbu-mtcs,
served as JSON by NYC Parks). Each entry has a park id ("Prop_ID"), a name, an
address or a description of where in the park, a type ("Run" or "Off-Leash")
and notes. It has no coordinates, so each park is placed with NYC Parks'
"Parks Properties" dataset (enfh-gkve): the pin goes at the middle of the park.
"""

import re
from decimal import Decimal
from html import unescape
from urllib.parse import urlencode

from .nyc_open_data import NYC_BOUNDS, _ring_centroid, center_of

DIRECTORY_URL = "https://www.nycgovparks.org/bigapps/DPR_DogRuns_001.json"
DATASET_URL = "https://data.cityofnewyork.us/d/ipbu-mtcs"
PROPERTIES_API = "https://data.cityofnewyork.us/resource/enfh-gkve.json"

# The first letter of a NYC Parks property id is its borough.
BOROUGHS = {
    "X": "Bronx",
    "B": "Brooklyn",
    "M": "Manhattan",
    "Q": "Queens",
    "R": "Staten Island",
}
DEFAULT_HOURS = "Off leash before 9 AM and after 9 PM"
EARLY_HOURS = "Off leash 6 AM – 9 AM only"
# "6:00 a.m. - 9:00 a.m. Only" or "6:00 a.m. to 9:00 a.m. only".
EARLY = re.compile(r"6:00\s*a\.?m\.?\s*(?:-|–|to)\s*9:00\s*a\.?m\.?\s*only", re.I)
# Directions rather than an address ("Except for playgrounds ... all areas of
# the park are off-leash"), shown as a feature instead.
DESCRIPTION = re.compile(r"^(except|though|all areas|throughout)\b", re.I)
MAX_ADDRESS = 90


def _clean(text):
    """Text without HTML tags, links or extra spaces."""
    text = re.sub(r"<a\b[^>]*>.*?</a>", "", text or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _sentences(text):
    # "9:00 a.m." isn't the end of a sentence.
    text = re.sub(
        r"\b([ap])\.m\.", lambda m: m.group(1).upper() + "M", text, flags=re.I
    )
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def properties_url(prop_ids):
    """The Parks Properties API URL for these park ids (one request)."""
    ids = ",".join(f"'{p}'" for p in sorted(prop_ids))
    return f"{PROPERTIES_API}?" + urlencode(
        {
            "$select": "gispropnum,signname,zipcode,multipolygon",
            "$where": f"gispropnum in ({ids})",
            "$limit": "1000",
        }
    )


def _inside(point, ring):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def middle(multipolygon):
    """A point inside the park's largest piece, as (lat, lng): its centroid,
    or, for a park shaped so the centroid falls outside (an L or a long curve),
    the middle of the widest stretch of the park across the centroid's
    latitude."""
    center = center_of(multipolygon)
    if center is None:
        return None
    y, x = center
    rings = [
        [(float(p[0]), float(p[1])) for p in polygon[0]]
        for polygon in multipolygon.get("coordinates", [])
        if polygon and polygon[0]
    ]
    ring = max(rings, key=lambda r: _ring_centroid(r)[0])
    if not _inside((x, y), ring):
        crossings = sorted(
            x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])
            if (y1 > y) != (y2 > y)
        )
        stretches = list(zip(crossings[::2], crossings[1::2]))
        if stretches:
            left, right = max(stretches, key=lambda s: s[1] - s[0])
            x = (left + right) / 2
    return _coordinate(y), _coordinate(x)


def _coordinate(value):
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def off_leash_areas(directory, properties):
    """One place per off-leash area in the directory, placed in its park.
    Entries that aren't off-leash areas, or whose park can't be found or is
    outside NYC, are left out."""
    parks = {p.get("gispropnum"): p for p in properties}
    (south, north), (west, east) = NYC_BOUNDS
    places = []
    seen = {}
    for entry in directory:
        if (entry.get("DogRuns_Type") or "").strip().lower() != "off-leash":
            continue
        prop_id = (entry.get("Prop_ID") or "").strip()
        park = parks.get(prop_id)
        point = middle(park.get("multipolygon")) if park else None
        if not point:
            continue
        latitude, longitude = point
        if not (south <= latitude <= north and west <= longitude <= east):
            continue

        raw_name = _clean(entry.get("Name"))
        early = bool(
            EARLY.search(raw_name)
            or EARLY.search(_clean(entry.get("Notes")))
            or EARLY.search(_clean(entry.get("Address")))
        )
        name = re.sub(r"\s*:\s*6:00.*$", "", raw_name)
        address = _clean(entry.get("Address"))
        # The hours are shown on their own line, so features are the rest.
        features = []
        if address and (DESCRIPTION.match(address) or len(address) > MAX_ADDRESS):
            features.append(address)
            address = ""
        # The notes as one line; links to PDFs and hours already shown are left out.
        notes = " ".join(
            sentence
            for sentence in _sentences(_clean(entry.get("Notes")))
            if not re.search(r"download|please see|hours", sentence, re.I)
        )
        if notes:
            features.append(notes)

        # A park can list the same area twice; each keeps its own id.
        source_id = f"{prop_id}-{_slug(name)}"[:60]
        seen[source_id] = seen.get(source_id, 0) + 1
        if seen[source_id] > 1:
            source_id = f"{source_id}-{seen[source_id]}"
        places.append(
            {
                "source_id": source_id,
                "name": name[:150],
                "address": address[:200],
                # The park's name, shown when there's no address.
                "neighborhood": _clean(park.get("signname"))[:100],
                "borough": BOROUGHS.get(prop_id[:1].upper(), ""),
                "zip_code": (park.get("zipcode") or "").split(",")[0].strip()[:20],
                "latitude": latitude,
                "longitude": longitude,
                "hours": EARLY_HOURS if early else DEFAULT_HOURS,
                "features": "\n".join(features),
            }
        )
    return sorted(places, key=lambda p: (p["name"], p["source_id"]))
