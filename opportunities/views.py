from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CareOpportunityForm
from .models import CareOpportunity
from django.urls import reverse


def _render_opportunity_list(
    request, *, selected_id=None, edit_form=None, editing=False
):
    """Render the owner dashboard, including its optional inline edit form."""
    opportunities = list(
        CareOpportunity.objects.filter(owner=request.user)
        .select_related("pet", "pet__pet_type", "service_type")
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

    return render(
        request,
        "opportunities/opportunity_list.html",
        {
            "open_posts": open_posts,
            "closed_posts": closed_posts,
            "selected": selected,
            "editing": bool(selected and editing),
            "just_closed": request.GET.get("closed") == "1",
            "just_reopened": request.GET.get("reopened") == "1",
            "edit_form": edit_form,
            "active_requests_tab": "care_posts",
        },
    )


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

    return redirect(f"{reverse('opportunities:list')}?post={opportunity.pk}&closed=1")


@login_required
@require_POST
def opportunity_reopen(request, pk):
    """Reopen an owner's closed post."""
    opportunity = get_object_or_404(CareOpportunity, pk=pk, owner=request.user)
    if opportunity.status == CareOpportunity.Status.CLOSED:
        opportunity.status = CareOpportunity.Status.OPEN
        opportunity.save(update_fields=["status"])
        messages.success(request, "Your care post has been reopened.")
    return redirect(f"{reverse('opportunities:list')}?post={opportunity.pk}&reopened=1")
