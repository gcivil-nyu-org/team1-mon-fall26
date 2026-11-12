"""#68 Browse Forum Posts: the newest posts first, and a page for each post.
#67 Create Forum Post: a form that publishes a post to the forum."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .authors import describe
from .forms import PostForm
from .models import BODY_LENGTH, TITLE_LENGTH, Post

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


@login_required
def post_create(request):
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        messages.success(request, "Your post is published.")
        return redirect("forum:detail", pk=post.pk)
    return render(
        request,
        "forum/post_form.html",
        {"form": form, "title_length": TITLE_LENGTH, "body_length": BODY_LENGTH},
    )
