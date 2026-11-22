"""Community forum, laid out as in Kat's 11/12 Figma: the Forum page lists
recent posts on the left and shows the selected post with its comments on
the right.

#68 Browse Forum Posts: recent posts, filtered by topic, and the whole post.
#67 Create Forum Post: a form that publishes a post to the forum.
#69 Comment on Forum Posts: comments under the selected post.
#102 Remove Inappropriate Forum Content: admins open the forum from
Explore and remove a post or comment, after a confirm popup (Kat's Figma
"Remove Inappropriate Forum Content"). It's hidden from everyone.
#103 Restrict Forum Posting: an account an admin restricted can still read
the forum, but can't write posts or comments (Figma "Restricted User").
#104 Pin Helpful Forum Posts: admins pin a post so it shows under "Pinned" at
the top of the forum for everyone, and unpin it again (Kat's Figma "Pin
Helpful Forum Posts" and "Unpin Forum Posts")."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.restriction import is_forum_restricted
from staff.accounts import can_restrict
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
# #104: the banner after pinning or unpinning, with the Figma's wording.
PIN_DONE = {
    "pinned": "Post pinned. It now shows at the top of the forum.",
    "unpinned": "Post unpinned. It no longer shows at the top of the forum.",
}


def _posts():
    """Posts that are still up: removed ones (#102) are hidden from everyone."""
    return Post.objects.visible().select_related(*AUTHOR)


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
    posts = _posts().annotate(comment_count=VISIBLE_COMMENTS)
    if topic:
        posts = posts.filter(topic=topic)
    # #104: pinned posts sit above the recent ones, on the first page.
    page = Paginator(
        posts.unpinned().order_by("-created_at", "-pk"), PER_PAGE
    ).get_page(request.GET.get("page"))
    pinned = list(posts.pinned()) if page.number == 1 else []
    for post in [*pinned, *page]:
        describe(post)

    if selected is None:
        wanted = request.GET.get("post", "")
        if wanted.isdigit():
            selected = _posts().filter(pk=wanted).first()
        if selected is None:
            shown = [*pinned, *page.object_list]
            selected = shown[0] if shown else None

    comments = []
    if selected is not None:
        describe(selected)
        comments = [
            describe(comment)
            for comment in selected.comments.visible().select_related(*AUTHOR)
        ]

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
            "pinned": pinned,
            "topic": topic,
            "topics": topics,
            "selected": selected,
            "comments": comments,
            "form": form or CommentForm(),
            "new_comment": int(new_comment) if new_comment.isdigit() else None,
            "my_initials": initials(request.user),
            "my_theme": theme(request.user),
            "just_posted": just_posted,
            "post_form": post_form,
            # Admins look after the forum from Explore (Figma "Monitor Forum
            # Activity"): they don't write posts or comments there.
            "admin": admin,
            # #103: no New post or comment box for a restricted account.
            "can_post": not is_forum_restricted(request.user),
            # #103: admins can restrict the author's forum posting.
            "can_restrict_author": admin
            and selected is not None
            and can_restrict(request.user, selected.author)
            and not is_forum_restricted(selected.author),
            # #102: Remove asks for confirmation in a popup first.
            "confirm_post": admin and _to_confirm(request, "remove_post", selected),
            "confirm_comment": admin
            and _to_confirm(request, "remove_comment", selected, comments),
            "removed": REMOVED.get(request.GET.get("done")) if admin else None,
            "pin_done": PIN_DONE.get(request.GET.get("done")) if admin else None,
        },
    )


def _to_confirm(request, key, selected, comments=()):
    """The post (or one of its comments) the Remove popup is about."""
    pk = request.GET.get(key, "")
    if selected is None or not pk.isdigit():
        return None
    items = comments if key == "remove_comment" else [selected]
    return next((item for item in items if item.pk == int(pk)), None)


@login_required
def post_list(request):
    return _forum(request)


@login_required
def post_detail(request, pk):
    """Old links to a post open it on the Forum page."""
    return redirect(post_url(get_object_or_404(_posts(), pk=pk)))


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
        # #103: the Forum page says why New post is greyed out.
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
    """#102: an admin removes a spam or abusive post. No one sees it (or its
    comments) anymore, so the Forum page opens on the newest post."""
    post = get_object_or_404(Post, pk=pk)
    _remove(post)
    return redirect(f"{reverse('forum:list')}?done=post_removed")


@require_POST
@staff_required
def remove_comment(request, pk):
    """#102: an admin removes a spam or abusive comment."""
    comment = get_object_or_404(Comment.objects.select_related("post"), pk=pk)
    _remove(comment)
    return redirect(f"{post_url(comment.post)}&done=comment_removed")


@require_POST
@staff_required
def pin_post(request, pk):
    """#104: an admin pins a helpful post to the top of the forum. Only posts
    still up can be pinned: removed ones (#102) give Not found."""
    post = get_object_or_404(_posts(), pk=pk)
    if post.pinned_at is None:
        post.pinned_at = timezone.now()
        post.pinned_by = request.user
        post.save(update_fields=["pinned_at", "pinned_by"])
    return redirect(f"{post_url(post)}&done=pinned")


@require_POST
@staff_required
def unpin_post(request, pk):
    """#104: the post goes back among the recent posts."""
    post = get_object_or_404(Post, pk=pk)
    if post.pinned_at is not None:
        post.pinned_at = None
        post.pinned_by = None
        post.save(update_fields=["pinned_at", "pinned_by"])
    return redirect(f"{post_url(post)}&done=unpinned")
