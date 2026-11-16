"""Admin Announcements page and the banner users close.

Like the Reports page: tabs for Published and Drafts, the list on the left and
the selected announcement (or the form) on the right. Actions come back with
?done=<action> for the green banner, and Remove asks first with ?confirm=remove.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from staff.views import staff_required

from .forms import AnnouncementForm
from .models import Announcement, AnnouncementDismissal

PUBLISHED = "published"
DRAFTS = "drafts"
TABS = [(PUBLISHED, "Published"), (DRAFTS, "Drafts")]

# The banner after an action (Figma wording), keyed by ?done=.
DONE = {
    "published": "Published. Users will see the announcement on their home page.",
    "drafted": "Saved to Drafts.",
    "saved": "Changes saved.",
    "removed": "Announcement removed.",
    "deleted": "Draft deleted.",
}


def _tab_for(announcement):
    return PUBLISHED if announcement.is_published else DRAFTS


def _in_tab(tab):
    if tab == PUBLISHED:
        return Announcement.objects.published().order_by("-published_at", "-pk")
    return Announcement.objects.drafts().order_by("-updated_at", "-pk")


def _render(request, tab, selected=None, form=None, editing=None):
    counts = {
        PUBLISHED: Announcement.objects.published().count(),
        DRAFTS: Announcement.objects.drafts().count(),
    }
    return render(
        request,
        "announcements/manage.html",
        {
            "section": "announcements",
            "tab": tab,
            "tabs": [
                {"key": key, "label": label, "count": counts[key], "active": key == tab}
                for key, label in TABS
            ],
            "announcements": list(_in_tab(tab)),
            "selected": selected,
            "form": form,
            "editing": editing,
            "confirm_remove": (
                selected is not None and request.GET.get("confirm") == "remove"
            ),
            "done": DONE.get(request.GET.get("done")),
            "kinds": Announcement.Kind.choices,
            "audiences": Announcement.Audience.choices,
        },
    )


def _done(announcement, action):
    url = reverse("announcements:detail", args=[announcement.pk])
    return redirect(f"{url}?done={action}")


def _save(request, form, announcement=None):
    """Save the form as a draft or publish it, by the button pressed."""
    item = form.save(commit=False)
    if announcement is None:
        item.created_by = request.user
    if request.POST.get("action") == "publish" and not item.is_published:
        item.status = Announcement.Status.PUBLISHED
        item.published_at = timezone.now()
        item.save()
        return _done(item, "published")
    item.save()
    return _done(item, "saved" if item.is_published else "drafted")


@staff_required
def manage(request):
    tab = request.GET.get("tab", PUBLISHED)
    if tab not in dict(TABS):
        tab = PUBLISHED
    return _render(request, tab, _in_tab(tab).first())


@staff_required
def detail(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    return _render(request, _tab_for(announcement), announcement)


@staff_required
def create(request):
    """New announcement: Publish, or Save draft."""
    if request.method == "POST":
        publishing = request.POST.get("action") == "publish"
        form = AnnouncementForm(request.POST, publishing=publishing)
        if form.is_valid():
            return _save(request, form)
    else:
        form = AnnouncementForm()
    tab = request.GET.get("tab", PUBLISHED)
    return _render(request, tab if tab in dict(TABS) else PUBLISHED, form=form)


@staff_required
def edit(request, pk):
    """Edit an announcement. A published one stays published (Save changes);
    a draft can be saved again or published."""
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == "POST":
        publishing = (
            announcement.is_published or request.POST.get("action") == "publish"
        )
        form = AnnouncementForm(
            request.POST, instance=announcement, publishing=publishing
        )
        if form.is_valid():
            return _save(request, form, announcement)
    else:
        form = AnnouncementForm(instance=announcement)
    return _render(
        request, _tab_for(announcement), announcement, form=form, editing=announcement
    )


@staff_required
@require_POST
def publish(request, pk):
    """Publish a draft from its page, if it has everything it needs."""
    announcement = get_object_or_404(Announcement, pk=pk)
    if announcement.is_published:
        return _done(announcement, "published")
    form = AnnouncementForm(
        {
            "title": announcement.title,
            "kind": announcement.kind,
            "audience": announcement.audience,
            "message": announcement.message,
        },
        instance=announcement,
        publishing=True,
    )
    if not form.is_valid():
        # Missing fields: open the form with the errors showing.
        return _render(request, DRAFTS, announcement, form=form, editing=announcement)
    announcement.status = Announcement.Status.PUBLISHED
    announcement.published_at = timezone.now()
    announcement.save()
    return _done(announcement, "published")


@staff_required
@require_POST
def remove(request, pk):
    """Remove a published announcement or delete a draft. Users stop seeing it."""
    announcement = get_object_or_404(Announcement, pk=pk)
    action = "removed" if announcement.is_published else "deleted"
    tab = _tab_for(announcement)
    announcement.delete()
    url = reverse("announcements:manage")
    return redirect(f"{url}?tab={tab}&done={action}")


@login_required
@require_POST
def dismiss(request, pk):
    """The × on the banner: stop showing this announcement to this user."""
    announcement = get_object_or_404(Announcement.objects.published(), pk=pk)
    AnnouncementDismissal.objects.get_or_create(
        announcement=announcement, user=request.user
    )
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        back = reverse("home")
    return redirect(back)
