"""Admin pages for PawPal accounts (#89 View User Accounts, #90 Search,
#91 View User Account Details, #92 Restrict or Reinstate)."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.restriction import is_restricted, reinstate, restrict

from .accounts import (
    PER_PAGE,
    all_accounts,
    can_restrict,
    describe,
    details,
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


# After restricting or reinstating, the account page shows a banner (?done=).
DONE_STATUS = {"restricted": "restricted", "reinstated": "active"}


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
    }
    if selected is not None:
        done = request.GET.get("done")
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
            done=done if DONE_STATUS.get(done) == selected.status_key else "",
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
