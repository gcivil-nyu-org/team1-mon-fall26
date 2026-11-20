"""Community forum, laid out as in Kat's 11/12 Figma: the Forum page lists
recent posts on the left and shows the selected post with its comments on
the right.

#68 Browse Forum Posts: recent posts, filtered by topic, and the whole post.
#67 Create Forum Post: a form that publishes a post to the forum.
#69 Comment on Forum Posts: comments under the selected post.
#102 Remove Inappropriate Forum Content: admins remove a post or comment,
after a confirm popup. Users don't see it anymore; admins see it marked
Removed.
#103 Restrict Forum Posting: an account an admin restricted can still read
the forum, but can't write posts or comments."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.restriction import FORUM_RESTRICTED_MESSAGE, is_forum_restricted
from staff.views import staff_required

from .authors import describe, initials, theme
from .forms import CommentForm, PostForm
from .models import Comment, Post

PER_PAGE = 20
AUTHOR = ("author", "author__account_profile", "author__caregiver_profile")
# #102: comments users can see, for the comment counts.
VISIBLE_COMMENTS = Count("comments", filter=Q(comments__removed_at__isnull=True))
# After removing, the Forum page shows a banner (?done=).
REMOVED = {"post_removed": "Post", "comment_removed": "Comment"}


def _posts(user=None):
    """Posts this person can see: admins see removed ones too (#102)."""
    posts = Post.objects.select_related(*AUTHOR)
    if user is None or not user.is_staff:
        posts = posts.visible()
    return posts


def post_url(post):
    """The Forum page with this post open."""
    return f"{reverse('forum:list')}?post={post.pk}"


POSTED = "forum_just_posted"


def _forum(request, selected=None, form=None, post_form=None):
    topic = request.GET.get("topic", "")
    if topic not in Post.Topic.values:
        topic = ""
    # Meta.ordering isn't used once posts are grouped to count comments.
    admin = request.user.is_staff
    posts = (
        _posts(request.user)
        .annotate(comment_count=VISIBLE_COMMENTS)
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
            selected = _posts(request.user).filter(pk=wanted).first()
        if selected is None and page.object_list:
            selected = page.object_list[0]

    comments = []
    if selected is not None:
        describe(selected)
        comments = selected.comments.select_related(*AUTHOR)
        if not admin:
            comments = comments.visible()
        comments = [describe(comment) for comment in comments]

    new_comment = request.GET.get("new_comment", "")
    # Right after publishing: the "Posted!" banner and a NEW badge.
    just_posted = request.session.pop(POSTED, None)
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
            "comment_count": sum(1 for c in comments if c.removed_at is None),
            "form": form or CommentForm(),
            "new_comment": int(new_comment) if new_comment.isdigit() else None,
            "my_initials": initials(request.user),
            "my_theme": theme(request.user),
            "just_posted": just_posted,
            "post_form": post_form,
            # #102: Remove asks for confirmation in a popup first.
            "confirm_post": admin and _to_confirm(request, "remove_post", selected),
            "confirm_comment": admin
            and _to_confirm(request, "remove_comment", selected, comments),
            "removed": REMOVED.get(request.GET.get("done")) if admin else None,
            # #103: no New post button or comment box.
            "can_post": not is_forum_restricted(request.user),
            "restricted_message": FORUM_RESTRICTED_MESSAGE,
        },
    )


def _to_confirm(request, key, selected, comments=()):
    """The post (or one of its comments) the Remove popup is about, if it's
    still up."""
    pk = request.GET.get(key, "")
    if selected is None or not pk.isdigit():
        return None
    items = comments if key == "remove_comment" else [selected]
    return next(
        (item for item in items if item.pk == int(pk) and item.removed_at is None),
        None,
    )


@login_required
def post_list(request):
    return _forum(request)


@login_required
def post_detail(request, pk):
    """Old links to a post open it on the Forum page."""
    return redirect(post_url(get_object_or_404(_posts(request.user), pk=pk)))


@require_POST
@login_required
def add_comment(request, pk):
    # No new comments on a removed post (#102).
    post = get_object_or_404(_posts(), pk=pk)
    if is_forum_restricted(request.user):
        # #103: the Forum page says why there's no comment box.
        return redirect(post_url(post))
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
    """The "New post" popup over the Forum page (Figma "Create Forum Post")."""
    if is_forum_restricted(request.user):
        # #103: the Forum page says why there's no New post button.
        return redirect("forum:list")
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        request.session[POSTED] = post.pk
        return redirect(post_url(post))
    return _forum(request, post_form=form)


def _remove(item):
    if item.removed_at is None:
        item.removed_at = timezone.now()
        item.save(update_fields=["removed_at"])


@require_POST
@staff_required
def remove_post(request, pk):
    """#102: an admin removes a spam or abusive post. Users don't see it (or
    its comments) anymore."""
    post = get_object_or_404(Post, pk=pk)
    _remove(post)
    return redirect(f"{post_url(post)}&done=post_removed")


@require_POST
@staff_required
def remove_comment(request, pk):
    """#102: an admin removes a spam or abusive comment."""
    comment = get_object_or_404(Comment.objects.select_related("post"), pk=pk)
    _remove(comment)
    return redirect(
        f"{post_url(comment.post)}&done=comment_removed#comment-{comment.pk}"
    )
