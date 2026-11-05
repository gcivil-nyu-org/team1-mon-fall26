
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CareOpportunityForm
from .models import CareOpportunity, CareOpportunityInterest
from django.urls import reverse


def _render_opportunity_list(request, *, selected_id=None, edit_form=None, editing=False):
    """Render the owner dashboard, including its optional inline edit form."""
    opportunities = list(
        CareOpportunity.objects.filter(owner=request.user)
        .select_related("pet", "pet__pet_type", "service_type")
        .order_by("-created_at")
    )
    open_posts = [post for post in opportunities if post.status == CareOpportunity.Status.OPEN]
    closed_posts = [post for post in opportunities if post.status == CareOpportunity.Status.CLOSED]

    if selected_id is None:
        selected_id = request.GET.get("post")
    selected = next((post for post in opportunities if str(post.pk) == str(selected_id)), None)
    if selected is None and opportunities:
        selected = opportunities[0]

    if selected and editing and edit_form is None:
        edit_form = CareOpportunityForm(instance=selected, owner=request.user, lock_pet=True)

    # Show only active caregiver interest on the selected owner's care post.
    # The owner filter above ensures no other user's posts are exposed.
    interested_caregivers = (
        CareOpportunityInterest.objects.filter(opportunity=selected, is_active=True)
        .select_related("caregiver", "caregiver__user")
        .order_by("pk")
        if selected else CareOpportunityInterest.objects.none()
    )

    return render(request, "opportunities/opportunity_list.html", {
        "open_posts": open_posts,
        "closed_posts": closed_posts,
        "selected": selected,
        "editing": bool(selected and editing),
        "edit_form": edit_form,
        "active_requests_tab": "care_posts",
        "interested_caregivers": interested_caregivers,
    })


@login_required
def opportunity_list(request):
    """Owner dashboard with optional inline edit state."""
    return _render_opportunity_list(request, editing=request.GET.get("edit") == "1")


@login_required
def opportunity_create(request):
    """Create a public care post without selecting a caregiver."""

    if getattr(request.user, "caregiver_profile", None):
        messages.info(
            request,
            "Use a pet owner account to post care opportunities.",
        )
        return redirect("bookings:caregiver_requests")

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
        form = CareOpportunityForm(owner=request.user)

    return render(
        request,
        "opportunities/opportunity_form.html",
        {
            "form": form,
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
            messages.success(request, "Your care post has been updated!")
            return redirect(f"{reverse('opportunities:list')}?post={opportunity.pk}")
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

        messages.success(
            request,
            "Your care post has been closed.",
        )

    return redirect(
        f"{reverse('opportunities:list')}?post={opportunity.pk}"
    )



@login_required
@require_POST
def opportunity_reopen(request, pk):
    """Reopen an owner's closed care post."""
    opportunity = get_object_or_404(CareOpportunity, pk=pk, owner=request.user)
    if opportunity.status == CareOpportunity.Status.CLOSED:
        opportunity.status = CareOpportunity.Status.OPEN
        opportunity.save(update_fields=["status"])
        messages.success(request, "Your care post has been reopened.")
    return redirect(f"{reverse('opportunities:list')}?post={opportunity.pk}")


@login_required
def opportunity_browse(request):
    """Caregiver marketplace, with service and pet type filters."""
    from caregivers.models import CaregiverProfile, ServiceType
    from pets.models import PetType

    caregiver = CaregiverProfile.objects.filter(user=request.user).first()
    if caregiver is None:
        messages.info(request, "Create a caregiver profile to browse care opportunities.")
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

    posts = list(opportunities)
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
    for post in posts:
        post.caregiver_interested = post.pk in interested_ids

    return render(request, "opportunities/opportunity_browse.html", {
        "posts": posts,
        "selected": selected,
        "services": ServiceType.objects.order_by("name"),
        "pet_types": PetType.objects.order_by("name"),
        "selected_service": service,
        "selected_pet_type": pet_type,
        "interest_added": request.GET.get("interest") == "added",
        "interest_withdrawn": request.GET.get("interest") == "withdrawn",
        "active_requests_tab": "find_pets",
    })


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
