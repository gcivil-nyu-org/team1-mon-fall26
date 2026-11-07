"""Admin Reports page (story #95, laid out like Kat's Figma).

The list of reports sits on the left and the selected report on the right.
Two tabs: Open, and Resolved (reports an admin dismissed or acted on).
"""

from django.shortcuts import get_object_or_404, render

from staff.views import staff_required

from .models import Report

OPEN = "open"
RESOLVED = "resolved"
TABS = [(OPEN, "Open"), (RESOLVED, "Resolved")]


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
    return {"message": report.message}


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
    report = get_object_or_404(
        Report.objects.select_related(
            "reporter",
            "reported_user",
            "review__author",
            "review__booking__caregiver",
            "message__sender",
        ),
        pk=pk,
    )
    return _render(request, _tab_for(report), report)
