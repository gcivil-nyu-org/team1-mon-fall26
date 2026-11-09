"""Admin Reports page (story #95, laid out like Kat's Figma).

For a reported message, the page shows the whole conversation around it (#96).

The list of reports sits on the left and the selected report on the right.
Two tabs: Open, and Resolved (reports an admin dismissed or acted on).
Dismissing a report (#98) and removing the content (#97) each ask for
confirmation in a popup first.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from staff.views import staff_required

from messaging.models import Message

from .models import Report
from .moderation import dismiss, remove_content

OPEN = "open"
RESOLVED = "resolved"
TABS = [(OPEN, "Open"), (RESOLVED, "Resolved")]

# The confirm popups, opened with ?confirm=<action> on a report's page.
CONFIRM = {
    "dismiss": {
        "title": "Dismiss this report?",
        "text": "The {kind} stays up. The report will close as Dismissed.",
        "button": "Dismiss",
        "button_class": "btn-dark",
        "url": "reports:admin_dismiss",
    },
    "remove": {
        "title": "Remove this {kind}?",
        "text": "Users won't see it anymore. The report will close as Removed.",
        "button": "Remove",
        "button_class": "btn-danger",
        "url": "reports:admin_remove",
    },
}

# The banner shown after an action, keyed by ?done=<action>.
DONE = {
    "dismissed": "Report dismissed and moved to Resolved.",
    "removed": "{Kind} removed and moved to Resolved.",
}


def _in_tab(tab):
    reports = Report.objects.select_related("reporter", "reported_user")
    if tab == OPEN:
        return reports.filter(status=Report.Status.OPEN)
    return reports.exclude(status=Report.Status.OPEN)


def _tab_for(report):
    return OPEN if report.status == Report.Status.OPEN else RESOLVED


def _detail(report):
    """What the right-hand panel shows for one report."""
    if report.review_id:
        review = report.review
        return {
            "review": review,
            "where": review.booking.caregiver,
        }
    message = report.message
    if message is None:
        return {"message": None}
    # #96: the whole conversation, removed messages included, so admins can
    # see what led up to the reported message.
    conversation = (
        Message.objects.filter(conversation_id=message.conversation_id)
        .select_related("sender")
        .order_by("created_at", "pk")
    )
    return {"message": message, "conversation": conversation}


def _get(pk):
    return get_object_or_404(
        Report.objects.select_related(
            "reporter",
            "reported_user",
            "handled_by",
            "review__author",
            "review__booking__caregiver",
            "message__sender",
        ),
        pk=pk,
    )


def _render(request, tab, selected):
    open_count = Report.objects.filter(status=Report.Status.OPEN).count()
    tabs = [
        {
            "key": key,
            "label": label,
            "count": open_count if key == OPEN else Report.objects.count() - open_count,
            "active": key == tab,
        }
        for key, label in TABS
    ]
    context = {
        "tabs": tabs,
        "tab": tab,
        "reports": list(_in_tab(tab)),
        "selected": selected,
        "section": "reports",
    }
    if selected is not None:
        context.update(_detail(selected))
        kind = selected.get_kind_display().lower()
        confirm = CONFIRM.get(request.GET.get("confirm"))
        if confirm and selected.is_open:
            context["confirm"] = {
                **confirm,
                "title": confirm["title"].format(kind=kind),
                "text": confirm["text"].format(kind=kind),
                "url": reverse(confirm["url"], args=[selected.pk]),
            }
        done = DONE.get(request.GET.get("done"))
        context["done"] = done and done.format(Kind=kind.capitalize())
        # Figma: green after removing, gray after dismissing.
        context["done_dismissed"] = request.GET.get("done") == "dismissed"
    return render(request, "reports/admin_reports.html", context)


@staff_required
def report_list(request):
    tab = request.GET.get("status", OPEN)
    if tab not in dict(TABS):
        tab = OPEN
    reports = _in_tab(tab)
    return _render(request, tab, reports.first())


@staff_required
def report_detail(request, pk):
    report = _get(pk)
    # Right after Remove or Dismiss, stay on Open so the next report is one
    # click away; the panel still shows the one just handled (Figma).
    if request.GET.get("done") in DONE:
        return _render(request, OPEN, report)
    return _render(request, _tab_for(report), report)


def _after(request, report, done):
    if done is None:
        messages.info(request, "This report was already handled.")
        return redirect("reports:admin_detail", pk=report.pk)
    return redirect(reverse("reports:admin_detail", args=[report.pk]) + f"?done={done}")


@staff_required
@require_POST
def report_dismiss(request, pk):
    """#98: the content is fine, so close the report and keep the content up."""
    report = _get(pk)
    if not report.is_open:
        return _after(request, report, None)
    dismiss(report, request.user)
    return _after(request, report, "dismissed")


@staff_required
@require_POST
def report_remove(request, pk):
    """#97: the content breaks the rules, so hide it from users and close the report."""
    report = _get(pk)
    if not report.is_open:
        return _after(request, report, None)
    remove_content(report, request.user)
    return _after(request, report, "removed")
