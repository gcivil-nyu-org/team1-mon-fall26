"""Dog parks from NYC Open Data (story: Use Reliable Location Data).

The source is NYC Parks' official "Dog Runs" dataset (hxx3-bwgv):
https://data.cityofnewyork.us/d/hxx3-bwgv
Each row is one dog run, with its name, a unique id ("system"), the NYC Parks
property it's in ("gispropnum"), a borough code, ZIP code(s), its outline as a
MultiPolygon, and optional surface and seating.

It has no street address. Those come from NYC Parks' Directory of Dog Runs and
Off-Leash Areas (ipbu-mtcs), matched on the property id ("Prop_ID") and name.
Runs the directory doesn't clearly match show their neighborhood instead.
"""

import json
import re
from html import unescape
from urllib.error import URLError
from urllib.request import Request, urlopen

from caregivers.search import nearest_neighborhood

DATASET_ID = "hxx3-bwgv"
DATASET_URL = f"https://data.cityofnewyork.us/d/{DATASET_ID}"
API_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.geojson?$limit=5000"
DIRECTORY_URL = "https://www.nycgovparks.org/bigapps/DPR_DogRuns_001.json"
DIRECTORY_DATASET_URL = "https://data.cityofnewyork.us/d/ipbu-mtcs"
TIMEOUT_SECONDS = 30

BOROUGHS = {
    "M": "Manhattan",
    "B": "Brooklyn",
    "X": "Bronx",
    "Q": "Queens",
    "R": "Staten Island",
}

# Roughly the five boroughs; a point outside came from bad data.
NYC_BOUNDS = ((40.4, 41.0), (-74.3, -73.6))


class OpenDataUnavailable(Exception):
    """NYC Open Data could not be reached or sent something that isn't GeoJSON."""


def download(url=API_URL):
    """The current dog runs as GeoJSON (or, given its URL, the directory of
    dog runs as JSON). Raises OpenDataUnavailable."""
    request = Request(url, headers={"User-Agent": "PawPal (NYU course project)"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as error:
        raise OpenDataUnavailable(str(error)) from error


def _ring_centroid(ring):
    """Area and centroid (lng, lat) of one polygon ring (shoelace formula).
    Measured from the first corner, which keeps the arithmetic precise."""
    x0, y0 = ring[0]
    ring = [(x - x0, y - y0) for x, y in ring]
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    area /= 2
    if area == 0:
        xs, ys = zip(*ring)
        return 0.0, (x0 + sum(xs) / len(xs), y0 + sum(ys) / len(ys))
    return abs(area), (x0 + cx / (6 * area), y0 + cy / (6 * area))


def center_of(geometry):
    """(latitude, longitude) at the middle of a GeoJSON Point, Polygon or
    MultiPolygon, or None. For several polygons, the largest one is used."""
    if not geometry:
        return None
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    try:
        if kind == "Point":
            lng, lat = coords[:2]
            return float(lat), float(lng)
        polygons = {"Polygon": [coords], "MultiPolygon": coords}.get(kind)
        if not polygons:
            return None
        rings = [
            [(float(p[0]), float(p[1])) for p in polygon[0]] for polygon in polygons
        ]
        _, (lng, lat) = max((_ring_centroid(ring) for ring in rings if ring))
    except (TypeError, ValueError, IndexError):
        return None
    return lat, lng


def _in_nyc(lat, lng):
    (lat_min, lat_max), (lng_min, lng_max) = NYC_BOUNDS
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _features(row):
    """What the dataset says about the run, as the lines the detail card shows."""
    lines = ["Fenced off-leash dog run"]
    surface = (row.get("surface") or "").strip()
    if surface:
        lines.append(f"{surface.capitalize()} surface")
    if (row.get("seating") or "").strip().lower() == "yes":
        lines.append("Seating for people")
    return lines


# Words that don't tell two dog runs in the same park apart.
COMMON_WORDS = {
    "and", "area", "dog", "dogs", "for", "large", "leash", "level", "lower",
    "north", "of", "off", "park", "playground", "run", "runs", "s", "small",
    "south", "the", "upper",
}  # fmt: skip
# Directory "addresses" that describe the whole park rather than a place.
VAGUE_ADDRESSES = ("all areas", "except")
MAX_ADDRESS_LENGTH = 90


def _words(name):
    return set(re.findall(r"[a-z0-9]+", unescape(name or "").lower())) - COMMON_WORDS


def _street_numbers(text):
    """Numbered streets mentioned, e.g. {"105", "72"} for "West 105th, W. 72nd St"."""
    return set(re.findall(r"\b(\d+)(?:st|nd|rd|th)?\b", (text or "").lower()))


def _clean_address(text, run_name):
    """The directory's address for this run, or "" when it's missing, isn't
    really an address, or names other streets than the run's own name does."""
    text = " ".join(unescape(text or "").split()).strip(" ,")
    if len(text) > MAX_ADDRESS_LENGTH or text.lower().startswith(VAGUE_ADDRESSES):
        return ""
    numbers = _street_numbers(run_name)
    if numbers and _street_numbers(text) and not numbers & _street_numbers(text):
        return ""  # e.g. "66th Street Dog Run" vs. an entry at W. 72nd St
    # One entry for several runs: "Riverside Drive at West 72nd, West 87th,
    # West 105th" becomes "Riverside Drive at West 105th" for the 105th Street run.
    shared = re.match(r"^(.* at )(.+,.+)$", text)
    if shared and numbers:
        parts = [part.strip() for part in shared.group(2).split(",")]
        mine = [part for part in parts if numbers & _street_numbers(part)]
        if len(mine) == 1:
            return shared.group(1) + mine[0]
    return text


def _directory_entry(run_name, runs_in_park, entries):
    """The directory entry for one run, or None when it isn't clear which."""
    words = _words(run_name)
    if len(entries) == 1:
        entry = entries[0]
        covers_several = re.search(r"\(\d+ runs\)", entry["Name"] or "")
        if len(runs_in_park) == 1 or covers_several or _words(entry["Name"]) <= words:
            return entry
        return None
    scores = sorted(
        ((len(_words(e["Name"]) & words), i) for i, e in enumerate(entries)),
        reverse=True,
    )
    if (
        scores
        and scores[0][0] > 0
        and (len(scores) == 1 or scores[1][0] < scores[0][0])
    ):
        return entries[scores[0][1]]
    return None


def add_addresses(runs, directory):
    """Fill in each run's "address" from the NYC Parks directory of dog runs."""
    entries_by_park = {}
    for entry in directory or []:
        if (entry.get("DogRuns_Type") or "").lower() == "off-leash":
            continue  # off-leash lawns are other places in the park
        entries = entries_by_park.setdefault((entry.get("Prop_ID") or "").strip(), [])
        if entry not in entries:
            entries.append(entry)
    runs_by_park = {}
    for run in runs:
        runs_by_park.setdefault(run["park_id"], []).append(run)
    for run in runs:
        entries = entries_by_park.get(run["park_id"], []) if run["park_id"] else []
        entry = _directory_entry(run["name"], runs_by_park[run["park_id"]], entries)
        run["address"] = _clean_address(entry["Address"], run["name"]) if entry else ""


def dog_runs(geojson, directory=None):
    """The dog runs in a GeoJSON FeatureCollection from the dataset, ready to
    save as places. Rows without a name or a usable location are skipped.
    With the NYC Parks directory, each run also gets an "address"."""
    runs = []
    for feature in geojson.get("features") or []:
        row = feature.get("properties") or {}
        name = " ".join((row.get("name") or "").split())
        status = (row.get("featurestatus") or "Active").strip().lower()
        center = center_of(feature.get("geometry"))
        if not name or status != "active" or center is None or not _in_nyc(*center):
            continue
        source_id = row.get("system") or (
            f"objectid-{row['objectid']}" if row.get("objectid") else ""
        )
        if not source_id:
            continue
        lat, lng = center
        runs.append(
            {
                "source_id": source_id,
                "name": name,
                "borough": BOROUGHS.get(
                    (row.get("borough") or "").strip(), row.get("borough") or ""
                ),
                "zip_code": (row.get("zipcode") or "")[:20],
                "neighborhood": nearest_neighborhood(lat, lng)["name"],
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "features": "\n".join(_features(row)),
                "park_id": (row.get("gispropnum") or "").strip(),
            }
        )
    if directory is not None:
        add_addresses(runs, directory)
    for run in runs:
        del run["park_id"]
    return runs
