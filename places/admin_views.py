"""Admin "Pet-friendly places" page (story #107, Manage Pet-Friendly Location
Information; Figma "Manage Pet-Friendly Location" frames).

Laid out like the other admin pages: the places on the left, the selected one
on the right. Two tabs: All, and Hidden (places users can't see). Admins can
fix a place's details and hours, and hide or show it. Reports about a place
are handled on the Reports page.
"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from caregivers.geocoding import HOUSE_NUMBER, GeocodingUnavailable, geocode
from staff.views import staff_required

from .forms import PlaceForm, split_borough
from .models import Place, PlaceReport

ALL = "all"
HIDDEN = "hidden"
TABS = [(ALL, "All"), (HIDDEN, "Hidden")]
PER_PAGE = 20

# The banner shown after an action, keyed by ?done=<action>.
DONE = {
    "saved": "Changes saved. Users see the update.",
    "saved_pin": "Changes saved. We couldn't find the new address on the map, "
    "so the pin stayed where it was.",
    "shown": "Place shown. Users can see it again.",
}


def _places(tab, query):
    places = Place.objects.annotate(
        open_reports=Count("reports", filter=Q(reports__status=PlaceReport.Status.OPEN))
    )
    if tab == HIDDEN:
        places = places.filter(is_active=False)
    if query:
        places = places.filter(
            Q(name__icontains=query)
            | Q(address__icontains=query)
            | Q(neighborhood__icontains=query)
            | Q(borough__icontains=query)
            | Q(zip_code__icontains=query)
        )
    # Places with reports to look at come first.
    return places.order_by("-open_reports", "name", "pk")


def _tab_and_query(request):
    tab = request.GET.get("tab", ALL)
    if tab not in dict(TABS):
        tab = ALL
    return tab, request.GET.get("q", "").strip()


def _keep(tab, query):
    """The list's query string, kept on links to a place."""
    params = {}
    if query:
        params["q"] = query
    if tab != ALL:
        params["tab"] = tab
    return urlencode(params)


def _render(request, selected, form=None, confirm_hide=False):
    tab, query = _tab_and_query(request)
    places = _places(tab, query)
    page = Paginator(places, PER_PAGE).get_page(request.GET.get("page"))
    if selected is None:
        selected = page.object_list[0] if page.object_list else None
    open_reports = None
    if selected is not None:
        open_reports = list(
            PlaceReport.objects.filter(place=selected, status=PlaceReport.Status.OPEN)
        )
    context = {
        "tabs": [
            {
                "key": key,
                "label": label,
                "count": (
                    Place.objects.count()
                    if key == ALL
                    else Place.objects.filter(is_active=False).count()
                ),
            }
            for key, label in TABS
        ],
        "tab": tab,
        "query": query,
        "keep": _keep(tab, query),
        "page": page,
        "selected": selected,
        "week": selected.week() if selected else [],
        "open_now": selected.is_open_now() if selected else None,
        "open_reports": open_reports,
        "form": form,
        "confirm_hide": confirm_hide and selected is not None and selected.is_active,
        "done": DONE.get(request.GET.get("done")),
        "section": "places",
    }
    return render(request, "places/manage.html", context)


def _back(place, request, done=None):
    """The place's admin page, keeping the list's search and tab."""
    tab, query = _tab_and_query(request)
    params = _keep(tab, query)
    if done:
        params = f"{params}&done={done}" if params else f"done={done}"
    return reverse("places:manage_detail", args=[place.pk]) + (
        f"?{params}" if params else ""
    )


@staff_required
def manage(request):
    return _render(request, None)


@staff_required
def manage_detail(request, pk):
    place = get_object_or_404(Place, pk=pk)
    return _render(request, place, confirm_hide=request.GET.get("confirm") == "hide")


def _move_pin(place, typed):
    """Point the map pin at a new address. Returns False when it can't be
    found (the pin stays put). Only addresses with a house number are looked
    up, since GeoSearch guesses for anything else."""
    street, borough = split_borough(typed)
    place.address = street
    if borough:
        place.borough = borough
    if not HOUSE_NUMBER.match(street):
        return False
    try:
        location = geocode(f"{street}, {place.borough}" if place.borough else street)
    except GeocodingUnavailable:
        return False
    if location is None:
        return False
    place.latitude = location.latitude
    place.longitude = location.longitude
    place.borough = location.borough or place.borough
    place.neighborhood = location.neighborhood or place.neighborhood
    return True


@staff_required
def edit(request, pk):
    place = get_object_or_404(Place, pk=pk)
    if request.method != "POST":
        return _render(request, place, form=PlaceForm(place=place))

    form = PlaceForm(
        request.POST, place=place, amenities=request.POST.getlist("amenity")
    )
    if not form.is_valid():
        return _render(request, place, form=form)

    data = form.cleaned_data
    pin_moved = True
    if form.address_changed():
        pin_moved = _move_pin(place, data["address"])
    place.name = data["name"]
    place.category = data["category"]
    weekly_hours = form.weekly_hours()
    if weekly_hours or place.weekly_hours:
        place.weekly_hours = weekly_hours
        # Day-by-day hours replace hours written out as text.
        place.hours = ""
    place.features = "\n".join(form.amenities)
    place.edited_at = timezone.now()
    place.save()
    return redirect(_back(place, request, "saved" if pin_moved else "saved_pin"))


@staff_required
@require_POST
def hide(request, pk):
    """Figma "Hide Place": users stop seeing it on Explore."""
    place = get_object_or_404(Place, pk=pk)
    place.is_active = False
    place.edited_at = timezone.now()
    place.save(update_fields=["is_active", "edited_at", "updated_at"])
    return redirect(_back(place, request))


@staff_required
@require_POST
def show(request, pk):
    place = get_object_or_404(Place, pk=pk)
    place.is_active = True
    place.edited_at = timezone.now()
    place.save(update_fields=["is_active", "edited_at", "updated_at"])
    return redirect(_back(place, request, "shown"))
