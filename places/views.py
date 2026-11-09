"""Explore nearby: pet-friendly places and dog parks on a map (the Figma
"View Nearby Pet-Friendly Locations" and "View Nearby Dog Parks" frames)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from caregivers.search import DISTANCE_CHOICES, neighborhoods
from caregivers.views import _choice, _with, _without

from .models import MAX_REPORT_LENGTH, Place, PlaceReport
from .search import NAMES, find_origin, places_near

DEFAULT_DISTANCE = 1  # miles, as in the design
# Search fields both Explore pages share, kept when switching between them.
SHARED_FIELDS = ("location", "distance", "lat", "lng", "here")


def explore_url(name, params):
    """The other Explore page, keeping the location and distance."""
    kept = params.copy()
    for key in list(kept):
        if key not in SHARED_FIELDS:
            kept.pop(key)
    query = kept.urlencode()
    return reverse(name) + (f"?{query}" if query else "")


def _count_label(count, category):
    one, many = NAMES[category]
    return f"{count} {one if count == 1 else many}"


@login_required
def explore_places(request):
    params = request.GET
    if params.get("looking_for") == "caregivers":
        return redirect(explore_url("caregiver_list", params))

    category = params.get("category", "")
    if category not in Place.Category.values:
        category = ""
    distance = _choice(params.get("distance"), DISTANCE_CHOICES, DEFAULT_DISTANCE)
    origin, notice = find_origin(params)
    current = params.get("here") == "1" and origin is not None

    places = Place.objects.shown()
    if category:
        places = places.filter(category=category)
    if origin is not None:
        results = places_near(places, origin["latitude"], origin["longitude"], distance)
    else:
        results = list(places)

    # The headings name the area as typed ("Carroll Gardens"), not the full
    # neighborhood name it matched ("Carroll Gardens-Cobble Hill-...").
    typed = params.get("location", "").strip()
    if origin is None:
        origin_name = ""
    elif typed and not current:
        origin_name = typed.split(",")[0].strip()
    else:
        origin_name = origin["label"].split(",")[0].strip()

    picked = params.get("place", "")
    selected = next((p for p in results if str(p.pk) == picked), None)
    if selected is None and results:
        selected = results[0]

    chip_params = params.copy()
    chip_params.pop("place", None)
    chips = [
        {
            "label": label,
            "active": value == category,
            "query": (
                _with(chip_params, category=value)
                if value
                else _without(chip_params, "category")
            ),
        }
        for value, label in [("", "All")]
        + [(c, NAMES[c][1].capitalize()) for c in Place.Category.values]
    ]

    return render(
        request,
        "places/explore.html",
        {
            "places": results,
            "selected": selected,
            "category": category,
            "category_names": NAMES[category],
            "count_label": _count_label(len(results), category),
            "chips": chips,
            "origin": origin,
            "origin_name": origin_name,
            "notice": notice,
            "location_text": "" if current else params.get("location", "").strip(),
            "current": current,
            "distance": distance,
            "distance_choices": DISTANCE_CHOICES,
            "any_places": Place.objects.shown().exists(),
            "query_without_place": _without(params, "place"),
            "neighborhood_options": [
                {
                    "label": f"{n['name']}, {n['borough']}",
                    "latitude": n["latitude"],
                    "longitude": n["longitude"],
                }
                for n in neighborhoods()
            ],
            "map_data": {
                "places": [
                    {
                        "id": p.pk,
                        "name": p.name,
                        "category": p.category,
                        "latitude": float(p.latitude),
                        "longitude": float(p.longitude),
                    }
                    for p in results
                ],
                "selected": selected.pk if selected else None,
                "origin": (
                    {
                        "latitude": float(origin["latitude"]),
                        "longitude": float(origin["longitude"]),
                    }
                    if origin
                    else None
                ),
                "distance": distance,
                "carto_key": settings.CARTO_BASEMAPS_KEY,
            },
        },
    )


@login_required
def report_place(request, pk):
    """Report wrong info: tell the PawPal team a place's details are wrong."""
    place = get_object_or_404(Place.objects.shown(), pk=pk)
    back = request.POST.get("next") or request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        back = ""
    back = back or f"{reverse('places:explore')}?place={place.pk}"

    details = ""
    error = ""
    if request.method == "POST":
        details = request.POST.get("details", "").strip()
        if not details:
            error = "Tell us what's wrong so we can fix it."
        elif len(details) > MAX_REPORT_LENGTH:
            error = f"Keep it to {MAX_REPORT_LENGTH} characters."
        else:
            PlaceReport.objects.create(
                place=place, reporter=request.user, details=details
            )
            messages.success(
                request, f"Thanks! We'll check the information for {place.name}."
            )
            return redirect(back)

    return render(
        request,
        "places/report.html",
        {
            "place": place,
            "details": details,
            "error": error,
            "back": back,
            "max_length": MAX_REPORT_LENGTH,
        },
    )
