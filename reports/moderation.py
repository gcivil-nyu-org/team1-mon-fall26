"""What admins decide about a report: dismiss it (#98) or remove the content (#97).

A decision is about the reported review or message, so it closes every open
report about that same content, not just the one the admin opened.
"""

from django.utils import timezone

from .models import Report


def close_reports(report, *, status, admin):
    """Mark all open reports about this content as handled. Returns how many."""
    return (
        report.same_content()
        .filter(status=Report.Status.OPEN)
        .update(status=status, handled_by=admin, handled_at=timezone.now())
    )


def dismiss(report, admin):
    """The content is fine: close the reports and leave the content up."""
    return close_reports(report, status=Report.Status.DISMISSED, admin=admin)
