"""Admin pages for PawPal accounts (#89 View User Accounts, #90 Search)."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .accounts import PER_PAGE, all_accounts, describe, search


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
    return render(request, "staff/user_detail.html", {"account": account})
