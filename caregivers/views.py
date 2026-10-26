from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET
from django.urls import reverse
from .models import CaregiverProfile, CaregiverService
from .forms import CaregiverProfileForm, CaregiverServicesForm
from .geocoding import GeocodingUnavailable, autocomplete, geocode
from .search import (
    DEFAULT_DISTANCE,
    DISTANCE_CHOICES,
    SORT_CHOICES,
    caregivers_matching_text,
    caregivers_near,
    find_neighborhood,
    find_zip_code,
    nearby_suggestions,
    nearest_neighborhood,
    neighborhood,
    neighborhoods,
    offered_service_types,
    offering_service,
    put_service_first,
    searchable_caregivers,
    sort_caregivers,
)


def _neighborhood_label(neighborhood, borough):
    """ "Park Slope", "Brooklyn" -> "Park Slope, Brooklyn"."""
    return ", ".join(part for part in (neighborhood, borough) if part)


@login_required
@require_GET
def address_suggestions(request):
    """NYC addresses that start like ?q=, for the profile form's address box."""
    try:
        suggestions = autocomplete(request.GET.get("q", ""))
    except GeocodingUnavailable:
        suggestions = []
    return JsonResponse({
        "suggestions": [
            {
                "address": s.address,
                "neighborhood": _neighborhood_label(s.neighborhood, s.borough),
            }
            for s in suggestions
        ]
    })


@login_required
@require_GET
def address_neighborhood(request):
    """The neighborhood of ?address=, to fill in the profile form's Neighborhood box."""
    try:
        location = geocode(request.GET.get("address", ""))
    except GeocodingUnavailable:
        location = None
    label = _neighborhood_label(location.neighborhood, location.borough) if location else ""
    return JsonResponse({"neighborhood": label})


def save_selected_services(caregiver, selected):
    """Services picked on the profile form are offered right away, with or
    without a price. Unpicked ones are switched off but keep their details."""
    selected_ids = {service_type.pk for service_type in selected}
    for service_type in selected:
        offer, created = CaregiverService.objects.get_or_create(
            caregiver=caregiver, service_type=service_type
        )
        if not created and not offer.is_active:
            offer.is_active = True
            offer.save(update_fields=["is_active"])
    CaregiverService.objects.filter(caregiver=caregiver, is_active=True).exclude(
        service_type_id__in=selected_ids
    ).update(is_active=False)


@login_required
def create_caregiver_profile(request):
    # Each account has at most one caregiver profile.
    existing = getattr(request.user, "caregiver_profile", None)
    if existing:
        return redirect("caregiver", pk=existing.pk)

    if request.method == "POST":
        form = CaregiverProfileForm(request.POST, request.FILES)

        if form.is_valid():
            caregiver = form.save(commit=False)
            caregiver.user = request.user
            caregiver.save()
            form.save_m2m()
            if form.geocoding_unavailable:
                messages.warning(
                    request,
                    "Your profile was saved, but we couldn't look up your address "
                    "right now, so you won't appear in map search yet. "
                    "Please save your profile again later.",
                )

            save_selected_services(caregiver, form.cleaned_data["selected_services"])

            return redirect("caregiver", pk=caregiver.pk)

    else:
        # Start from the name they signed up with.
        form = CaregiverProfileForm(initial={
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
        })

    return render(
        request,
        "caregivers/create_profile.html",
        {"form": form}
    )


@login_required
def edit_caregiver_profile(request, pk):
    caregiver = get_object_or_404(CaregiverProfile, pk=pk, user=request.user)

    if request.method == "POST":
        form = CaregiverProfileForm(
            request.POST,
            request.FILES,
            instance=caregiver
        )

        if form.is_valid():
            caregiver = form.save()
            if form.geocoding_unavailable:
                messages.warning(
                    request,
                    "Your profile was saved, but we couldn't look up your address "
                    "right now, so you won't appear in map search yet. "
                    "Please save your profile again later.",
                )

            save_selected_services(caregiver, form.cleaned_data["selected_services"])

            return redirect("caregiver", pk=caregiver.pk)

    else:
        existing_services = CaregiverService.objects.filter(
            caregiver=caregiver, is_active=True
        ).values_list("service_type_id", flat=True)

        form = CaregiverProfileForm(
            instance=caregiver,
            initial={
                "selected_services": existing_services
            }
        )

    return render(
        request,
        "caregivers/create_profile.html",
        {
            "form": form,
            "caregiver": caregiver,
        }
    )


@login_required
def delete_caregiver_service(request, pk, service_id):
    # Like the other service pages, only the caregiver themselves can delete.
    caregiver = get_object_or_404(CaregiverProfile, pk=pk, user=request.user)

    service = get_object_or_404(
        CaregiverService,
        pk=service_id,
        caregiver=caregiver
    )

    if request.method == "POST":
        service.delete()
        return redirect("services", pk=caregiver.pk)

    return render(
        request,
        "caregivers/delete_service.html",
        {
            "caregiver": caregiver,
            "service": service,
        }
    )


def caregiver_profile_detail(request, pk):
    caregiver = get_object_or_404(CaregiverProfile, pk=pk)

    # Only services the caregiver currently offers (unpicked ones are switched off).
    provided_services = CaregiverService.objects.filter(
        caregiver=caregiver, is_active=True
    ).select_related("service_type")

    service_listings = provided_services.filter(
        is_active=True,
        price__isnull=False
    )

    return render(
        request,
        "caregivers/profile_detail.html",
        {
            "caregiver": caregiver,
            # A caregiver viewing their own profile gets Edit, not the request card.
            "is_own": bool(caregiver.user_id) and caregiver.user_id == request.user.id,
            "provided_services": provided_services,
            "service_listings": service_listings,
        }
    )


@login_required
def caregiver_list_services(request, pk):
    caregiver = get_object_or_404(CaregiverProfile, pk=pk, user=request.user)
    services = CaregiverService.objects.filter(caregiver=caregiver)
    return render(request, "caregivers/list_services.html", {"services": services, "caregiver": caregiver})


@login_required
def add_caregiver_service(request, pk):
    caregiver = get_object_or_404(CaregiverProfile, pk=pk, user=request.user)

    if request.method == "POST":
        form = CaregiverServicesForm(request.POST)

        if form.is_valid():
            service_type = form.cleaned_data["service_type"]

            already_exists = CaregiverService.objects.filter(
                caregiver=caregiver,
                service_type=service_type
            ).exists()

            if already_exists:
                form.add_error(
                    "service_type",
                    "You already have this service! Please edit your existing listing instead."
                )
            else:
                service = form.save(commit=False)
                service.caregiver = caregiver
                service.save()

                return redirect("services", pk=caregiver.pk)

    else:
        form = CaregiverServicesForm()

    return render(
        request,
        "caregivers/add_service.html",
        {
            "form": form,
            "caregiver": caregiver,
        }
    )


@login_required
def edit_caregiver_service(request, pk, service_id):
    caregiver = get_object_or_404(CaregiverProfile, pk=pk, user=request.user)

    service = get_object_or_404(
        CaregiverService,
        pk=service_id,
        caregiver=caregiver
    )

    if request.method == "POST":
        form = CaregiverServicesForm(request.POST, instance=service)

        if form.is_valid():
            form.save()
            return redirect("services", pk=caregiver.pk)
    else:
        form = CaregiverServicesForm(instance=service)

    return render(
        request,
        "caregivers/edit_service.html",
        {
            "form": form,
            "caregiver": caregiver,
            "service": service,
        }
    )


# Availability (#35) follows the caregiver's "Accepting new bookings" setting.
# The page only shows available caregivers; ?availability=any lists everyone
# (kept for a future filter control).
AVAILABILITY_CHOICES = ("available", "any")


@login_required
def caregiver_list(request):
    """Story #33: owners search caregivers near a neighborhood, ZIP code,
    address or their current location.

    Results can be filtered by service (#34) and availability (#35), limited
    by distance and sorted.
    """
    params = request.GET
    notice = ""

    availability = params.get("availability", "available")
    if availability not in AVAILABILITY_CHOICES:
        availability = "available"
    caregivers = searchable_caregivers(
        request.user, available_only=availability == "available"
    )

    # Service (#34): only caregivers who list it.
    service_types = offered_service_types()
    service_code = params.get("service", "").strip()
    service = None
    if service_code:
        service = next(
            (st for st in service_types if str(st.pk) == service_code), None
        )
        if service is None:
            notice = "Choose a service from the list."
            service_code = ""
        else:
            caregivers = offering_service(caregivers, service)

    distance = _choice(params.get("distance"), DISTANCE_CHOICES, DEFAULT_DISTANCE)
    sort = params.get("sort", "closest")
    if sort not in SORT_CHOICES:
        sort = "closest"

    # Where the owner is searching from. `address` is the old name of `location`.
    text = (params.get("location") or params.get("address") or "").strip()
    area_code = params.get("area", "").strip()
    current = params.get("here") == "1"
    latitude, longitude = _coordinates(params)

    origin = None  # {"label", "latitude", "longitude"}
    results = None
    if current:
        if latitude is None:
            notice = (
                "Your current location isn't in New York City. "
                "Enter a neighborhood or ZIP code instead."
            )
        else:
            hood = nearest_neighborhood(latitude, longitude)
            origin = {
                "label": f"you ({hood['name']})",
                "latitude": latitude,
                "longitude": longitude,
            }
    elif latitude is not None and text:
        # Picked from the suggestions in the browser.
        origin = {"label": text, "latitude": latitude, "longitude": longitude}
    elif text:
        place = _place_for(text)
        if place is None:
            try:
                location = geocode(text)
            except GeocodingUnavailable:
                location = None
                results = caregivers_matching_text(caregivers, text)
                notice = (
                    "Address search is unavailable right now, so these results "
                    "match the neighborhood name instead."
                )
            else:
                if location is None:
                    notice = (
                        "We couldn't find that place in New York City. Try a "
                        "neighborhood, ZIP code or street address."
                    )
                    results = []
                else:
                    place = {
                        "label": text,
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                    }
        origin = place
    elif area_code:
        area = neighborhood(area_code)
        if area is None:
            notice = "Choose a neighborhood from the list."
        else:
            origin = {
                "label": f"{area['name']}, {area['borough']}",
                "latitude": area["latitude"],
                "longitude": area["longitude"],
            }

    suggestions = []
    if origin is not None:
        results = caregivers_near(
            caregivers, origin["latitude"], origin["longitude"], max_miles=distance
        )
        if not results:
            suggestions = nearby_suggestions(
                caregivers, float(origin["latitude"]), float(origin["longitude"]), distance
            )
    elif results is None:
        results = list(caregivers)
    results = sort_caregivers(results, sort, has_origin=origin is not None)
    if service is not None:
        put_service_first(results, service)

    map_points = [
        {
            "id": c.pk,
            "name": c.name,
            "latitude": float(c.latitude),
            "longitude": float(c.longitude),
            "url": reverse("caregiver", args=[c.pk]),
        }
        for c in results
        if c.latitude is not None and c.longitude is not None
    ]
    searched = bool(text or area_code or current)
    return render(
        request,
        "caregivers/caregiver_list.html",
        {
            "caregivers": results,
            "location_text": "" if current else text,
            "area_code": area_code,
            "current": current,
            "origin": origin,
            "notice": notice,
            "searched": searched,
            "suggestions": suggestions,
            "distance": distance,
            "distance_choices": DISTANCE_CHOICES,
            "sort": sort,
            "sort_choices": SORT_CHOICES.items(),
            "service_types": service_types,
            "service": service,
            "availability": availability,
            "show_map": params.get("map") == "1",
            "query_without_service": _without(params, "service"),
            # One chip per service (#34); each link keeps the rest of the search.
            "service_filters": [
                {"type": st, "query": _with(params, service=st.pk)}
                for st in service_types
            ],
            "neighborhood_options": [
                {
                    "label": f"{n['name']}, {n['borough']}",
                    "latitude": n["latitude"],
                    "longitude": n["longitude"],
                }
                for n in neighborhoods()
            ],
            "map_data": {
                "points": map_points,
                "origin": (
                    {
                        "latitude": float(origin["latitude"]),
                        "longitude": float(origin["longitude"]),
                    }
                    if origin
                    else None
                ),
            },
        },
    )


def _place_for(text):
    """A neighborhood or ZIP code the owner typed, as an origin, or None."""
    hood = find_neighborhood(text)
    if hood is not None:
        return {
            "label": f"{hood['name']}, {hood['borough']}",
            "latitude": hood["latitude"],
            "longitude": hood["longitude"],
        }
    return find_zip_code(text)


def _choice(value, choices, default):
    """An int from the query string if it's one of the choices, else the default."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number in choices else default


def _without(params, *keys):
    """This search's query string without the given keys."""
    kept = params.copy()
    for key in keys:
        kept.pop(key, None)
    return kept.urlencode()


def _with(params, **values):
    """This search's query string with the given keys set (or replaced)."""
    kept = params.copy()
    for key, value in values.items():
        kept[key] = str(value)
    return kept.urlencode()


def _coordinates(params):
    """Latitude/longitude from the query string, or (None, None) if missing or invalid."""
    try:
        latitude = float(params.get("lat", ""))
        longitude = float(params.get("lng", ""))
    except ValueError:
        return None, None
    # Roughly the five boroughs; anything else came from a tampered URL.
    if not (40.4 <= latitude <= 41.0 and -74.3 <= longitude <= -73.6):
        return None, None
    return latitude, longitude
