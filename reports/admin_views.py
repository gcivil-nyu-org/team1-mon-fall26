"""Admin pages for reported content (story #95: view open reports and reasons)."""

from collections import Counter

from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from staff.views import staff_required

from .models import Report

# The tabs on the reports page, in order: (status in the address, label).
TABS = [
    ("open", "Open"),
    ("dismissed", "Dismissed"),
    ("resolved", "Removed"),
    ("all", "All"),
]


def _with_counts(reports):
    """How many open reports each review or message has, to help prioritize."""
    open_reports = Report.objects.filter(status=Report.Status.OPEN)
    by_review = Counter(
        open_reports.filter(review__isnull=False).values_list("review_id", flat=True)
    )
    by_message = Counter(
        open_reports.filter(message__isnull=False).values_list("message_id", flat=True)
    )
    for report in reports:
        if report.review_id:
            report.times_reported = by_review.get(report.review_id, 1)
        elif report.message_id:
            report.times_reported = by_message.get(report.message_id, 1)
        else:
            report.times_reported = 1
    return reports


@staff_required
def report_list(request):
    status = request.GET.get("status", "open")
    if status not in dict(TABS):
        status = "open"
    reports = Report.objects.select_related("reporter", "reported_user")
    if status != "all":
        reports = reports.filter(status=status)
    counts = Counter(Report.objects.values_list("status", flat=True))
    tabs = [
        {
            "status": key,
            "label": label,
            "count": sum(counts.values()) if key == "all" else counts.get(key, 0),
            "active": key == status,
        }
        for key, label in TABS
    ]
    return render(
        request,
        "reports/admin_list.html",
        {
            "reports": _with_counts(list(reports)),
            "tabs": tabs,
            "status": status,
            "section": "reports",
        },
    )


def _where(report):
    """A link to where the reported content appears, when there is one."""
    if report.review_id:
        return reverse("caregiver", args=[report.review.booking.caregiver_id])
    return None


@staff_required
def report_detail(request, pk):
    report = get_object_or_404(
        Report.objects.select_related(
            "reporter", "reported_user", "review__booking", "message__conversation"
        ),
        pk=pk,
    )
    # Other people who reported the same review or message.
    target = report.review if report.kind == Report.Kind.REVIEW else report.message
    others = Report.objects.none()
    if target is not None:
        others = (
            Report.objects.filter(**{report.kind: target})
            .exclude(pk=report.pk)
            .select_related("reporter")
        )
    return render(
        request,
        "reports/admin_detail.html",
        {
            "report": report,
            "others": others,
            "where": _where(report),
            "section": "reports",
        },
    )
