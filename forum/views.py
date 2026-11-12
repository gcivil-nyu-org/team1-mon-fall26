"""#68 Browse Forum Posts: the newest posts first, and a page for each post."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .authors import describe
from .models import Post

PER_PAGE = 20


def _posts():
    return Post.objects.select_related(
        "author", "author__account_profile", "author__caregiver_profile"
    )


@login_required
def post_list(request):
    page = Paginator(_posts(), PER_PAGE).get_page(request.GET.get("page"))
    for post in page:
        describe(post)
    return render(request, "forum/post_list.html", {"page": page})


@login_required
def post_detail(request, pk):
    post = describe(get_object_or_404(_posts(), pk=pk))
    return render(request, "forum/post_detail.html", {"post": post})
