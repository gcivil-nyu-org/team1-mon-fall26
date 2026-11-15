"""#107 Manage Pet-Friendly Location Information: the admin "Pet-friendly
places" page under Explore, laid out like Kat's 11/12 Figma ("Pet-Friendly
Places (All)", "Hide Pet-Friendly Location", "Pet-Friendly Places (Hidden)"):
places on the left, the selected place on the right, and a way to hide a
place from users (or show it again)."""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from places.models import Place

from .views import staff_required

HIDDEN = "hidden"
PER_PAGE = 25
# Banners after hiding or showing a place (?done=...).
DONE = {"hidden": False, "shown": True}


def _places(tab="", query=""):
    places = Place.objects.annotate(
        open_reports=Count("reports", filter=Q(reports__is_resolved=False))
    ).order_by("name", "pk")
    if tab == HIDDEN:
        places = places.filter(is_active=False)
    if query:
        places = places.filter(
            Q(name__icontains=query)
            | Q(address__icontains=query)
            | Q(neighborhood__icontains=query)
            | Q(zip_code__icontains=query)
        )
    return places


def place_url(place, tab="", **params):
    query = QueryDict(mutable=True)
    for key, value in [("tab", tab), *params.items()]:
        if value:
            query[key] = value
    url = reverse("staff:place_detail", args=[place.pk])
    return f"{url}?{query.urlencode()}" if query else url


@staff_required
def place_list(request, pk=None):
    tab = HIDDEN if request.GET.get("tab") == HIDDEN else ""
    query = request.GET.get("q", "").strip()
    page = Paginator(_places(tab, query), PER_PAGE).get_page(request.GET.get("page"))
    if pk is not None:
        selected = get_object_or_404(_places(), pk=pk)
    else:
        selected = page[0] if page.object_list else None

    # The tab and search, kept on every link in the list.
    keep = QueryDict(mutable=True)
    if tab:
        keep["tab"] = tab
    if query:
        keep["q"] = query
    context = {
        "page": page,
        "query": query,
        "keep": keep.urlencode(),
        "tab": tab,
        "tabs": [
            {"key": "", "label": "All", "count": Place.objects.count()},
            {
                "key": HIDDEN,
                "label": "Hidden",
                "count": Place.objects.filter(is_active=False).count(),
            },
        ],
        "selected": selected,
    }
    if selected is not None:
        done = request.GET.get("done", "")
        context.update(
            # Hiding asks first, in a popup (?confirm=hide).
            confirm_hide=request.GET.get("confirm") == "hide" and selected.is_active,
            # The banner only shows while the place is still in that state.
            done=done if DONE.get(done) == selected.is_active else "",
        )
    return render(request, "staff/place_list.html", context)


@staff_required
def place_detail(request, pk):
    return place_list(request, pk=pk)


def _set_shown(request, pk, shown):
    place = get_object_or_404(Place, pk=pk)
    if place.is_active != shown:
        place.is_active = shown
        place.save(update_fields=["is_active", "updated_at"])
    tab = HIDDEN if request.POST.get("tab") == HIDDEN else ""
    query = request.POST.get("q", "").strip()
    return redirect(place_url(place, tab, q=query, done="shown" if shown else "hidden"))


@require_POST
@staff_required
def hide_place(request, pk):
    """Users stop seeing the place on Explore until an admin shows it again."""
    return _set_shown(request, pk, False)


@require_POST
@staff_required
def show_place(request, pk):
    return _set_shown(request, pk, True)
