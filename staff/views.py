"""Admin pages for PawPal accounts (#89 View User Accounts, #90 Search,
#91 View User Account Details, #92 Restrict or Reinstate)."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.restriction import is_restricted, reinstate, restrict

from .accounts import (
    PER_PAGE,
    all_accounts,
    can_restrict,
    describe,
    details,
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


@staff_required
def user_list(request):
    query = request.GET.get("q", "").strip()
    accounts = search(all_accounts(), query) if query else all_accounts()
    page = Paginator(accounts, PER_PAGE).get_page(request.GET.get("page"))
    for user in page:
        describe(user)
    return render(request, "staff/user_list.html", {"page": page, "query": query})


@staff_required
def user_detail(request, pk):
    account = describe(get_object_or_404(all_accounts(), pk=pk))
    return render(
        request,
        "staff/user_detail.html",
        {
            "account": account,
            **details(account),
            "can_restrict": can_restrict(request.user, account),
            "restrict_form": RestrictForm(),
        },
    )


def _restrictable(request, pk):
    account = get_object_or_404(all_accounts(), pk=pk)
    if not can_restrict(request.user, account):
        raise PermissionDenied
    return account


@require_POST
@staff_required
def restrict_user(request, pk):
    account = _restrictable(request, pk)
    form = RestrictForm(request.POST)
    if not is_restricted(account) and form.is_valid():
        restrict(account, form.cleaned_data["reason"])
        messages.success(
            request,
            f"{account.get_full_name() or account.username}'s account is restricted.",
        )
    return redirect("staff:user_detail", pk=account.pk)


@require_POST
@staff_required
def reinstate_user(request, pk):
    account = _restrictable(request, pk)
    if is_restricted(account):
        reinstate(account)
        messages.success(
            request,
            f"{account.get_full_name() or account.username}'s account is reinstated.",
        )
    return redirect("staff:user_detail", pk=account.pk)
