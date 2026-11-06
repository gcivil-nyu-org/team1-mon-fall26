"""Story #117: report an inappropriate review or message for admins to review."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from messaging.inbox import conversations_for
from messaging.models import Message
from reviews.models import Review
from reviews.templatetags.review_tags import reviewer_name

from .forms import ReportForm
from .models import Report

THANKS = "Thanks for letting us know. Our team will review it."
ALREADY = "You've already reported this. Our team will review it."


def _next_url(request, fallback):
    """Where to go after reporting: back to the page the report came from."""
    url = request.POST.get("next") or request.GET.get("next")
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return fallback


def _report(request, *, kind, target, author, text, about, back):
    """Show the report form for one review or message, and save it."""
    if author.pk == request.user.pk:
        raise Http404("You can't report your own content.")
    already = Report.objects.filter(reporter=request.user, **{kind: target}).exists()
    if already:
        messages.info(request, ALREADY)
        return redirect(back)

    form = ReportForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.reporter = request.user
        report.reported_user = author
        report.kind = kind
        setattr(report, kind, target)
        report.content_text = text
        report.save()
        messages.success(request, THANKS)
        return redirect(back)

    return render(
        request,
        "reports/report_form.html",
        {
            "form": form,
            "kind": kind,
            "about": about,
            "author_name": reviewer_name(author),
            "text": text,
            "back": back,
        },
    )


@login_required
def report_review(request, pk):
    review = get_object_or_404(
        Review.objects.select_related("author", "booking__caregiver"), pk=pk
    )
    fallback = reverse("caregiver", args=[review.booking.caregiver_id])
    return _report(
        request,
        kind="review",
        target=review,
        author=review.author,
        text=review.comment,
        about="review",
        back=_next_url(request, fallback),
    )


@login_required
def report_message(request, pk):
    # Only someone in the conversation can see, and so report, a message.
    message = get_object_or_404(
        Message.objects.select_related("sender", "conversation").filter(
            conversation__in=conversations_for(request.user)
        ),
        pk=pk,
    )
    fallback = message.conversation.get_absolute_url()
    return _report(
        request,
        kind="message",
        target=message,
        author=message.sender,
        text=message.body,
        about="message",
        back=_next_url(request, fallback),
    )
