"""#68 Browse Forum Posts: the newest posts first, and a page for each post.
#67 Create Forum Post: a form that publishes a post to the forum.
#69 Comment on Forum Posts: comments under each post."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .authors import describe
from .forms import CommentForm, PostForm
from .models import BODY_LENGTH, COMMENT_LENGTH, TITLE_LENGTH, Post

PER_PAGE = 20


def _posts():
    return Post.objects.select_related(
        "author", "author__account_profile", "author__caregiver_profile"
    )


@login_required
def post_list(request):
    # Meta.ordering isn't used once posts are grouped to count comments.
    posts = (
        _posts()
        .annotate(comment_count=Count("comments"))
        .order_by("-created_at", "-pk")
    )
    page = Paginator(posts, PER_PAGE).get_page(request.GET.get("page"))
    for post in page:
        describe(post)
    return render(request, "forum/post_list.html", {"page": page})


def _detail(request, post, form):
    comments = [
        describe(comment)
        for comment in post.comments.select_related(
            "author", "author__account_profile", "author__caregiver_profile"
        )
    ]
    return render(
        request,
        "forum/post_detail.html",
        {
            "post": describe(post),
            "comments": comments,
            "form": form,
            "comment_length": COMMENT_LENGTH,
        },
    )


@login_required
def post_detail(request, pk):
    return _detail(request, get_object_or_404(_posts(), pk=pk), CommentForm())


@require_POST
@login_required
def add_comment(request, pk):
    post = get_object_or_404(_posts(), pk=pk)
    form = CommentForm(request.POST)
    if not form.is_valid():
        return _detail(request, post, form)
    comment = form.save(commit=False)
    comment.post = post
    comment.author = request.user
    comment.save()
    return redirect(reverse("forum:detail", args=[post.pk]) + f"#comment-{comment.pk}")


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
