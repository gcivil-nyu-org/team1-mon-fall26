from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from caregivers.geocoding import distance_miles
from caregivers.search import find_neighborhood, neighborhoods
from messaging.models import Conversation
from reviews.models import Review, rating_summary

from accounts.roles import owners_only
from .forms import CareOpportunityForm
from .models import CareOpportunity, CareOpportunityInterest
from django.urls import reverse


def _neighborhood_options():
    """NYC neighborhoods for the Location box's suggestions, as on Explore."""
    return [{"label": f"{n['name']}, {n['borough']}"} for n in neighborhoods()]


def _render_opportunity_list(
    request, *, selected_id=None, edit_form=None, editing=False
):
    """Render the owner dashboard, including its optional inline edit form."""
    opportunities = list(
        CareOpportunity.objects.filter(owner=request.user)
        .select_related("pet", "pet__pet_type", "service_type")
        .annotate(
            interest_count=Count("interests", filter=Q(interests__is_active=True))
        )
        .order_by("-created_at")
    )
    open_posts = [
        post for post in opportunities if post.status == CareOpportunity.Status.OPEN
    ]
    closed_posts = [
        post for post in opportunities if post.status == CareOpportunity.Status.CLOSED
    ]

    if selected_id is None:
        selected_id = request.GET.get("post")
    selected = next(
        (post for post in opportunities if str(post.pk) == str(selected_id)), None
    )
    if selected is None and opportunities:
        selected = opportunities[0]

    if selected and editing and edit_form is None:
        edit_form = CareOpportunityForm(
            instance=selected, owner=request.user, lock_pet=True
        )

    # Show only active caregiver interest on the selected owner's care post.
    # The owner filter above ensures no other user's posts are exposed.
    interested_caregivers = (
        CareOpportunityInterest.objects.filter(opportunity=selected, is_active=True)
        .select_related("caregiver", "caregiver__user")
        .order_by("pk")
        if selected
        else CareOpportunityInterest.objects.none()
    )
    interested_caregivers = list(interested_caregivers)
    for interest in interested_caregivers:
        interest.rating = rating_summary(
            Review.objects.visible().filter(
                booking__caregiver=interest.caregiver, role=Review.Role.OWNER
            )
        )

    return render(
        request,
        "opportunities/opportunity_list.html",
        {
            "open_posts": open_posts,
            "closed_posts": closed_posts,
            "selected": selected,
            "editing": bool(selected and editing),
            "edit_form": edit_form,
            "neighborhood_options": _neighborhood_options() if editing else [],
            "active_requests_tab": "care_posts",
            "interested_caregivers": interested_caregivers,
            # In-panel feedback after closing, reopening or saving a post.
            "post_status": request.GET.get("status", ""),
        },
    )


@login_required
def opportunity_list(request):
    """Owner dashboard with optional inline edit state."""
    elsewhere = owners_only(
        request, "Use a pet owner account to post care opportunities."
    )
    if elsewhere is not None:
        return elsewhere
    return _render_opportunity_list(request, editing=request.GET.get("edit") == "1")


def _owner_location(user):
    """The owner's neighborhood as "Park Slope, Brooklyn", or ""."""
    profile = getattr(user, "account_profile", None)
    neighborhood = (getattr(profile, "neighborhood", "") or "").strip()
    if not neighborhood:
        return ""
    place = find_neighborhood(neighborhood)
    if place and place.get("borough") and "," not in neighborhood:
        return f"{neighborhood}, {place['borough']}"
    return neighborhood


@login_required
def opportunity_create(request):
    """Create a public care post without selecting a caregiver."""

    elsewhere = owners_only(
        request, "Use a pet owner account to post care opportunities."
    )
    if elsewhere is not None:
        return elsewhere

    if request.method == "POST":
        form = CareOpportunityForm(
            request.POST,
            owner=request.user,
        )

        if form.is_valid():
            opportunity = form.save(commit=False)
            opportunity.owner = request.user
            opportunity.save()

            return redirect(
                "opportunities:created",
                pk=opportunity.pk,
            )
    else:
        form = CareOpportunityForm(
            owner=request.user,
            initial={"location": _owner_location(request.user)},
        )

    return render(
        request,
        "opportunities/opportunity_form.html",
        {
            "form": form,
            "neighborhood_options": _neighborhood_options(),
            "active_requests_tab": "care_posts",
        },
    )


@login_required
def opportunity_created(request, pk):
    """Confirmation page after posting."""

    opportunity = get_object_or_404(
        CareOpportunity.objects.select_related(
            "pet",
            "pet__pet_type",
            "service_type",
        ),
        pk=pk,
        owner=request.user,
    )

    return render(
        request,
        "opportunities/opportunity_created.html",
        {
            "opportunity": opportunity,
            "active_requests_tab": "care_posts",
        },
    )


@login_required
def opportunity_edit(request, pk):
    """Save inline edits, or show the prefilled form in the dashboard."""
    opportunity = get_object_or_404(CareOpportunity, pk=pk, owner=request.user)
    if request.method == "POST":
        form = CareOpportunityForm(
            request.POST, instance=opportunity, owner=request.user, lock_pet=True
        )
        if form.is_valid():
            form.save()
            return redirect(
                f"{reverse('opportunities:list')}?post={opportunity.pk}&status=saved"
            )
        return _render_opportunity_list(
            request, selected_id=opportunity.pk, edit_form=form, editing=True
        )
    return redirect(f"{reverse('opportunities:list')}?post={opportunity.pk}&edit=1")


@login_required
@require_POST
def opportunity_close(request, pk):
    """Allow the owner to close their care opportunity."""

    opportunity = get_object_or_404(
        CareOpportunity,
        pk=pk,
        owner=request.user,
    )

    if opportunity.status == CareOpportunity.Status.OPEN:
        opportunity.status = CareOpportunity.Status.CLOSED
        opportunity.save(update_fields=["status"])

    return redirect(
        f"{reverse('opportunities:list')}?post={opportunity.pk}&status=closed"
    )


@login_required
@require_POST
def opportunity_reopen(request, pk):
    """Reopen an owner's closed care post."""
    opportunity = get_object_or_404(CareOpportunity, pk=pk, owner=request.user)
    if opportunity.status == CareOpportunity.Status.CLOSED:
        opportunity.status = CareOpportunity.Status.OPEN
        opportunity.save(update_fields=["status"])
    return redirect(
        f"{reverse('opportunities:list')}?post={opportunity.pk}&status=reopened"
    )


def _place_and_distance(location, origin):
    """Short place name ("Gowanus") and miles from where the caregiver is
    searching (or their own area), if both are known."""
    place_name = (location or "").split(",")[0].strip()
    place = find_neighborhood(location or "")
    if place is None or origin is None:
        return place_name, None
    miles = distance_miles(
        origin["latitude"], origin["longitude"], place["latitude"], place["longitude"]
    )
    return place_name, round(miles, 1)


def _browse_query(params, **values):
    """This search's query string with the given filters set; "" drops one."""
    kept = params.copy()
    for key in ("post", "interest", "looking_for"):
        kept.pop(key, None)
    for key, value in values.items():
        if value in ("", None):
            kept.pop(key, None)
        else:
            kept[key] = str(value)
    return kept.urlencode()


@login_required
def opportunity_browse(request):
    """Caregiver marketplace, with service and pet type filters.

    Figma "Find Pets": under Explore ("Looking for: Pets needing care"), with
    the same Location and Distance search as the other Explore pages. Without
    a search it lists every open post, nearest to the caregiver's own area.
    """
    from caregivers.models import CaregiverProfile, ServiceType
    from caregivers.search import DEFAULT_DISTANCE, DISTANCE_CHOICES
    from caregivers.views import _choice
    from pets.models import PetType
    from places.search import find_origin
    from places.views import explore_url

    params = request.GET
    looking_for = params.get("looking_for")
    if looking_for == "places":
        return redirect(explore_url("places:explore", params))
    if looking_for == "caregivers":
        return redirect(explore_url("caregiver_list", params))

    caregiver = CaregiverProfile.objects.filter(user=request.user).first()
    if caregiver is None:
        messages.info(
            request, "Create a caregiver profile to browse care opportunities."
        )
        return redirect("opportunities:list")

    opportunities = (
        CareOpportunity.objects.filter(
            status=CareOpportunity.Status.OPEN,
            pet__deleted_at__isnull=True,
        )
        .exclude(owner=request.user)
        .select_related("owner", "pet", "pet__pet_type", "service_type")
        .order_by("start_time", "pk")
    )
    service = request.GET.get("service", "")
    pet_type = request.GET.get("pet_type", "")
    if service.isdecimal():
        opportunities = opportunities.filter(service_type_id=int(service))
    if pet_type.isdecimal():
        opportunities = opportunities.filter(pet__pet_type_id=int(pet_type))

    distance = _choice(params.get("distance"), DISTANCE_CHOICES, DEFAULT_DISTANCE)
    origin, notice = find_origin(params)
    searched = origin is not None
    if origin is None and caregiver.latitude is not None:
        # No search yet: distances from the caregiver's own area.
        origin = {
            "label": caregiver.neighborhood or caregiver.service_area,
            "latitude": caregiver.latitude,
            "longitude": caregiver.longitude,
        }

    posts = []
    for post in opportunities:
        post.place_name, post.distance = _place_and_distance(post.location, origin)
        # A search only shows posts within the distance picked.
        if searched and (post.distance is None or post.distance > distance):
            continue
        posts.append(post)
    selected_id = request.GET.get("post", "")
    selected = next((post for post in posts if str(post.pk) == selected_id), None)
    if selected is None and posts:
        selected = posts[0]

    interested_ids = set(
        CareOpportunityInterest.objects.filter(
            caregiver=caregiver,
            is_active=True,
            opportunity_id__in=[post.pk for post in posts],
        ).values_list("opportunity_id", flat=True)
    )
    if selected is not None:
        owner = selected.owner
        # "Kat" for notes and buttons, "Kat W." next to the pet's details.
        selected.owner_first = owner.first_name or owner.username
        selected.owner_label = (
            f"{owner.first_name} {owner.last_name[:1].upper()}."
            if owner.first_name and owner.last_name
            else selected.owner_first
        )

    for post in posts:
        post.caregiver_interested = post.pk in interested_ids

    # The headings name the area as typed ("Park Slope").
    typed = params.get("location", "").strip()
    if not searched:
        origin_name = ""
    elif typed and params.get("here") != "1":
        origin_name = typed.split(",")[0].strip()
    else:
        origin_name = origin["label"].split(",")[0].strip()

    return render(
        request,
        "opportunities/opportunity_browse.html",
        {
            "posts": posts,
            "selected": selected,
            "services": ServiceType.objects.order_by("name"),
            "pet_types": PetType.objects.order_by("name"),
            "selected_service": service,
            "selected_pet_type": pet_type,
            "interest_added": request.GET.get("interest") == "added",
            "interest_withdrawn": request.GET.get("interest") == "withdrawn",
            "active_requests_tab": "find_pets",
            "caregiver_neighborhood": caregiver.neighborhood,
            # The purple Explore search (Figma "Find Pets").
            # Before a search, the box shows the caregiver's own area (Figma).
            "location_text": (
                ""
                if params.get("here") == "1"
                else typed or ("" if searched else caregiver.neighborhood)
            ),
            "distance": distance,
            "distance_choices": DISTANCE_CHOICES,
            "searched": searched,
            "origin_name": origin_name,
            "notice": notice,
            "neighborhood_options": [
                {
                    "label": f"{n['name']}, {n['borough']}",
                    "latitude": n["latitude"],
                    "longitude": n["longitude"],
                }
                for n in neighborhoods()
            ],
            # Each filter link keeps the rest of the search.
            "pet_filters": [
                {
                    "label": pet.name,
                    "query": _browse_query(params, pet_type=pet.pk),
                    "active": pet_type == str(pet.pk),
                }
                for pet in PetType.objects.order_by("name")
            ],
            "service_filters": [
                {
                    "label": st.name,
                    "query": _browse_query(params, service=st.pk),
                    "active": service == str(st.pk),
                }
                for st in ServiceType.objects.order_by("name")
            ],
            "all_pets_query": _browse_query(params, pet_type=""),
            "all_services_query": _browse_query(params, service=""),
            "post_query": _browse_query(params),
            "clear_filters_query": _browse_query(params, pet_type="", service=""),
        },
    )


def _caregiver_for_interest(request):
    from caregivers.models import CaregiverProfile

    return CaregiverProfile.objects.filter(user=request.user).first()


@login_required
@require_POST
def opportunity_interest(request, pk):
    caregiver = _caregiver_for_interest(request)
    if caregiver is None:
        messages.error(request, "A caregiver profile is required to express interest.")
        return redirect("opportunities:browse")

    opportunity = get_object_or_404(
        CareOpportunity,
        pk=pk,
        status=CareOpportunity.Status.OPEN,
        pet__deleted_at__isnull=True,
    )
    if opportunity.owner_id == request.user.pk:
        messages.error(request, "You cannot express interest in your own care post.")
        return redirect("opportunities:browse")

    interest, created = CareOpportunityInterest.objects.get_or_create(
        opportunity=opportunity,
        caregiver=caregiver,
        defaults={"is_active": True},
    )
    if not created and not interest.is_active:
        interest.is_active = True
        interest.save(update_fields=["is_active", "updated_at"])
    return redirect(f"{reverse('opportunities:browse')}?post={pk}&interest=added")


@login_required
@require_POST
def opportunity_withdraw_interest(request, pk):
    caregiver = _caregiver_for_interest(request)
    if caregiver is None:
        messages.error(request, "A caregiver profile is required.")
        return redirect("opportunities:browse")

    CareOpportunityInterest.objects.filter(
        opportunity_id=pk, caregiver=caregiver, is_active=True
    ).update(is_active=False)
    return redirect(f"{reverse('opportunities:browse')}?post={pk}&interest=withdrawn")


@login_required
def opportunity_message_owner(request, pk):
    """A caregiver opens a chat with the owner of an open care post."""
    caregiver = _caregiver_for_interest(request)
    if caregiver is None:
        messages.error(request, "A caregiver profile is required to message owners.")
        return redirect("opportunities:browse")
    opportunity = get_object_or_404(
        CareOpportunity,
        pk=pk,
        status=CareOpportunity.Status.OPEN,
        owner__is_active=True,
    )
    if opportunity.owner_id == request.user.pk:
        return redirect(f"{reverse('opportunities:browse')}?post={pk}")
    conversation, _ = Conversation.objects.get_or_create(
        owner=opportunity.owner, caregiver=caregiver, booking=None
    )
    return redirect(conversation)
