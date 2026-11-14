"""Community forum, laid out as in Kat's 11/12 Figma: the Forum page lists
recent posts on the left and shows the selected post with its comments on
the right.

#68 Browse Forum Posts: recent posts, filtered by topic, and the whole post.
#67 Create Forum Post: a form that publishes a post to the forum.
#69 Comment on Forum Posts: comments under the selected post."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .authors import describe, initials
from .forms import CommentForm, PostForm
from .models import BODY_LENGTH, TITLE_LENGTH, Post

PER_PAGE = 20


def _posts():
    return Post.objects.select_related(
        "author", "author__account_profile", "author__caregiver_profile"
    )


def post_url(post):
    """The Forum page with this post open."""
    return f"{reverse('forum:list')}?post={post.pk}"


def _forum(request, selected=None, form=None):
    topic = request.GET.get("topic", "")
    if topic not in Post.Topic.values:
        topic = ""
    # Meta.ordering isn't used once posts are grouped to count comments.
    posts = (
        _posts()
        .annotate(comment_count=Count("comments"))
        .order_by("-created_at", "-pk")
    )
    if topic:
        posts = posts.filter(topic=topic)
    page = Paginator(posts, PER_PAGE).get_page(request.GET.get("page"))
    for post in page:
        describe(post)

    if selected is None:
        wanted = request.GET.get("post", "")
        if wanted.isdigit():
            selected = _posts().filter(pk=wanted).first()
        if selected is None and page.object_list:
            selected = page.object_list[0]

    comments = []
    if selected is not None:
        describe(selected)
        comments = [
            describe(comment)
            for comment in selected.comments.select_related(
                "author", "author__account_profile", "author__caregiver_profile"
            )
        ]

    new_comment = request.GET.get("new_comment", "")
    topics = [{"value": "", "label": "All", "active": not topic}] + [
        {"value": value, "label": label, "active": value == topic}
        for value, label in Post.Topic.choices
    ]
    return render(
        request,
        "forum/forum.html",
        {
            "page": page,
            "topic": topic,
            "topics": topics,
            "selected": selected,
            "comments": comments,
            "form": form or CommentForm(),
            "new_comment": int(new_comment) if new_comment.isdigit() else None,
            "my_initials": initials(request.user),
        },
    )


@login_required
def post_list(request):
    return _forum(request)


@login_required
def post_detail(request, pk):
    """Old links to a post open it on the Forum page."""
    return redirect(post_url(get_object_or_404(Post, pk=pk)))


@require_POST
@login_required
def add_comment(request, pk):
    post = get_object_or_404(_posts(), pk=pk)
    form = CommentForm(request.POST)
    if not form.is_valid():
        return _forum(request, selected=post, form=form)
    comment = form.save(commit=False)
    comment.post = post
    comment.author = request.user
    comment.save()
    # The new comment is highlighted, as in the "Comment posted" frame.
    return redirect(f"{post_url(post)}&new_comment={comment.pk}#comment-{comment.pk}")


@login_required
def post_create(request):
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        messages.success(request, "Your post is published.")
        return redirect(post_url(post))
    return render(
        request,
        "forum/post_form.html",
        {"form": form, "title_length": TITLE_LENGTH, "body_length": BODY_LENGTH},
    )
