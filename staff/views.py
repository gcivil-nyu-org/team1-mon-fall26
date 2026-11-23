"""Admin pages for PawPal accounts (#89 View User Accounts, #90 Search,
#91 View User Account Details, #92 Restrict or Reinstate, #103 Restrict
Forum Posting)."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.deletion import delete_account
from accounts import restriction
from accounts.restriction import is_restricted, reinstate, restrict
from caregivers.models import ServiceType
from pets.models import PetType
from reports import moderation

from .accounts import (
    PER_PAGE,
    all_accounts,
    can_restrict,
    describe,
    details,
    history_reviews,
    restricted,
    search,
)
from .forms import RestrictForm


def staff_required(view):
    """Logged-out visitors go to Log in; logged-in non-admins get 403."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


# After restricting or reinstating, the account page shows a banner (?done=)
# while the account still has one of these statuses.
DONE_STATUS = {
    "restricted": ("restricted",),
    "reinstated": ("active", "forum_restricted"),  # #103: forum only
}
# After removing a review from the history (#99).
REVIEW_REMOVED = "review_removed"
# After restricting or restoring forum posting (#103): whether it's restricted.
FORUM_DONE = {"forum_restricted": True, "forum_restored": False}


@staff_required
def user_list(request, pk=None, restrict_form=None):
    """The Users page, laid out like Kat's Figma: accounts on the left, the
    selected account on the right. Without a selection, the first account in
    the list is shown.

    Two tabs, All and Restricted (#92); the search (#90) works in both.
    """
    query = request.GET.get("q", "").strip()
    tab = "restricted" if request.GET.get("tab") == "restricted" else "all"
    accounts = restricted(all_accounts()) if tab == "restricted" else all_accounts()
    if query:
        accounts = search(accounts, query)
    page = Paginator(accounts, PER_PAGE).get_page(request.GET.get("page"))
    for user in page:
        describe(user)
    if pk is not None:
        selected = describe(get_object_or_404(all_accounts(), pk=pk))
    else:
        selected = page[0] if page.object_list else None

    # The search and tab, kept on every link in the list.
    keep = QueryDict(mutable=True)
    if query:
        keep["q"] = query
    if tab == "restricted":
        keep["tab"] = tab
    tabs = [
        {"key": "all", "label": "All", "count": all_accounts().count()},
        {
            "key": "restricted",
            "label": "Restricted",
            "count": restricted(all_accounts()).count(),
        },
    ]
    context = {
        "page": page,
        "query": query,
        "tab": tab,
        "tabs": tabs,
        "keep": keep.urlencode(),
        "selected": selected,
        "pet_type_count": PetType.objects.count(),
        "service_type_count": ServiceType.objects.count(),
        # #93: after deleting an account, the page shows the next one with a
        # banner (?deleted=<pk>) while that account is still deleted.
        "deleted_account": _deleted_account(request),
    }
    if selected is not None:
        done = request.GET.get("done")
        forum_restricted = restriction.is_forum_restricted(selected)
        context.update(
            details(selected),
            can_restrict=can_restrict(request.user, selected),
            restrict_form=restrict_form or RestrictForm(),
            # Restrict asks for confirmation in a popup first (?confirm=restrict).
            # The popup opens again when the reason was left empty.
            confirm=(
                request.GET.get("confirm") == "restrict" or restrict_form is not None
            )
            and can_restrict(request.user, selected)
            and selected.status_key != "restricted",
            # The banner only shows while the account is still in that state.
            done=done if selected.status_key in DONE_STATUS.get(done, ()) else "",
            review_removed=done == REVIEW_REMOVED,
            # #93: deleting an account asks for confirmation first (?confirm=delete).
            confirm_delete=request.GET.get("confirm") == "delete"
            and can_restrict(request.user, selected),
            # #99: removing a review asks for confirmation first (?remove_review=<pk>).
            confirm_review=_review_to_confirm(request, selected),
            # #103: forum posting only, with its own popup (?confirm=forum).
            forum_restricted=forum_restricted,
            confirm_forum=request.GET.get("confirm") == "forum"
            and can_restrict(request.user, selected)
            and not forum_restricted,
            forum_done=done if FORUM_DONE.get(done) == forum_restricted else "",
        )
    return render(request, "staff/user_list.html", context)


@staff_required
def user_detail(request, pk):
    """One account, selected on the Users page (#91)."""
    return user_list(request, pk=pk)


def _restrictable(request, pk):
    account = get_object_or_404(all_accounts(), pk=pk)
    if not can_restrict(request.user, account):
        raise PermissionDenied
    return account


def _review_to_confirm(request, account):
    """The review the Remove popup is about, if it's in this account's
    history and still up."""
    pk = request.GET.get("remove_review", "")
    if not pk.isdigit():
        return None
    return (
        history_reviews(account)
        .filter(pk=pk, removed_at__isnull=True)
        .select_related("author", "booking__pet", "booking__service_type")
        .first()
    )


def _deleted_account(request):
    pk = request.GET.get("deleted", "")
    if not pk.isdigit():
        return None
    return (
        get_user_model()
        .objects.filter(pk=pk, is_staff=False, is_active=False)
        .select_related("caregiver_profile")
        .first()
    )


def _done(account, action):
    url = reverse("staff:user_detail", args=[account.pk])
    return redirect(f"{url}?done={action}")


@require_POST
@staff_required
def restrict_user(request, pk):
    account = _restrictable(request, pk)
    if is_restricted(account):
        return redirect("staff:user_detail", pk=account.pk)
    form = RestrictForm(request.POST)
    if not form.is_valid():
        # Show the popup again with the error.
        return user_list(request, pk=account.pk, restrict_form=form)
    restrict(account, form.cleaned_data["reason"])
    return _done(account, "restricted")


@require_POST
@staff_required
def reinstate_user(request, pk):
    account = _restrictable(request, pk)
    if not is_restricted(account):
        return redirect("staff:user_detail", pk=account.pk)
    reinstate(account)
    return _done(account, "reinstated")


@require_POST
@staff_required
def remove_review(request, pk, review_pk):
    """#99: remove an inappropriate review from the account's review history
    (#100). It's hidden from everyone like a review removed after a report."""
    account = get_object_or_404(all_accounts(), pk=pk)
    review = get_object_or_404(history_reviews(account), pk=review_pk)
    if review.removed_at is not None:
        return redirect("staff:user_detail", pk=account.pk)
    moderation.remove_review(review, request.user)
    return _done(account, REVIEW_REMOVED)


@require_POST
@staff_required
def delete_user(request, pk):
    """#93: an admin removes an account, for example after serious reports.

    It's the same as users deleting their own account (#48): they can't log
    in anymore, their open bookings close, and their address and photo are
    removed. Bookings and reviews other people can see stay. As in Kat's
    "Delete account" design, the account leaves the list and the page moves
    on to the first account, with a banner.
    """
    account = _restrictable(request, pk)
    delete_account(account)
    return redirect(f"{reverse('staff:user_list')}?deleted={account.pk}")


@staff_required
def manage_types(request):
    """Display pet and service types with their usage counts."""

    active_tab = "services" if request.GET.get("tab") == "services" else "pets"

    pet_types = PetType.objects.annotate(
        pet_count=Count("pet", distinct=True),
        caregiver_count=Count("caregiverprofile", distinct=True),
    ).order_by("name")

    service_types = ServiceType.objects.annotate(
        caregiver_count=Count(
            "caregiverservice__caregiver",
            distinct=True,
        ),
        booking_count=Count("bookings", distinct=True),
    ).order_by("name")

    # Determine which type should be selected.
    items = list(service_types if active_tab == "services" else pet_types)

    selected_id = request.GET.get("selected")

    selected = next(
        (item for item in items if str(item.pk) == selected_id),
        None,
    )

    # Select the first type by default, as shown in Figma.
    if selected is None and items:
        selected = items[0]

    context = {
        "active_tab": active_tab,
        "pet_types": pet_types,
        "service_types": service_types,
        "pet_type_count": pet_types.count(),
        "service_type_count": service_types.count(),
        "selected": selected,
    }

    return render(request, "staff/manage_types.html", context)


@require_POST
@staff_required
def rename_type(request):
    """Rename an existing pet or service type."""

    tab = request.POST.get("tab")
    type_id = request.POST.get("type_id")
    name = request.POST.get("name", "").strip()

    if tab == "pets":
        model = PetType
    elif tab == "services":
        model = ServiceType
    else:
        return HttpResponseBadRequest("Invalid type category.")

    if not type_id or not type_id.isdigit():
        return HttpResponseBadRequest("Invalid type ID.")

    item = get_object_or_404(model, pk=type_id)

    redirect_url = f"{reverse('staff:manage_types')}" f"?tab={tab}&selected={item.pk}"

    if not name:
        messages.error(request, "The name cannot be empty.")
        return redirect(redirect_url)

    if len(name) > 100:
        messages.error(request, "The name must be 100 characters or fewer.")
        return redirect(redirect_url)

    if model.objects.filter(name__iexact=name).exclude(pk=item.pk).exists():
        messages.error(request, f'"{name}" already exists.')
        return redirect(redirect_url)

    if item.name == name:
        return redirect(redirect_url)

    try:
        with transaction.atomic():
            item.name = name
            item.save(update_fields=["name"])
    except IntegrityError:
        messages.error(request, "That name already exists.")
        return redirect(redirect_url)

    messages.success(request, "Changes saved successfully.")
    return redirect(redirect_url)


@require_POST
@staff_required
def restrict_forum(request, pk):
    """#103: stop an account posting in the forum, for community violations,
    without restricting the whole account (#92)."""
    account = _restrictable(request, pk)
    if not restriction.is_forum_restricted(account):
        restriction.restrict_forum(account)
    return _done(account, "forum_restricted")


@require_POST
@staff_required
def add_type(request):
    """Create a new pet or service type."""

    tab = request.POST.get("tab")
    name = request.POST.get("name", "").strip()

    if tab == "pets":
        model = PetType
    elif tab == "services":
        model = ServiceType
    else:
        return HttpResponseBadRequest("Invalid type category.")

    redirect_url = f"{reverse('staff:manage_types')}?tab={tab}"

    if not name:
        messages.error(request, "The name cannot be empty.")
        return redirect(redirect_url)

    if len(name) > 100:
        messages.error(
            request,
            "The name must be 100 characters or fewer.",
        )
        return redirect(redirect_url)

    if model.objects.filter(name__iexact=name).exists():
        messages.error(
            request,
            f'"{name}" already exists.',
        )
        return redirect(redirect_url)

    try:
        with transaction.atomic():
            item = model.objects.create(name=name)
    except IntegrityError:
        messages.error(request, "That name already exists.")
        return redirect(redirect_url)

    messages.success(
        request,
        f'"{item.name}" added successfully!',
    )

    return redirect(f"{redirect_url}&selected={item.pk}")


@require_POST
@staff_required
def restore_forum(request, pk):
    """#103: let the account post in the forum again."""
    account = _restrictable(request, pk)
    restriction.restore_forum(account)
    return _done(account, "forum_restored")
