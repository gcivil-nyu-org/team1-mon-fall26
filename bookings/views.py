from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import dateformat, timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from caregivers.models import CaregiverProfile

from .forms import BookingRequestForm
from .models import Booking

RELATED = ("owner", "pet__pet_type", "caregiver", "service_type")


def owner_bookings(user):
    """Bookings the signed-in owner made, with the related records preloaded."""
    return Booking.objects.filter(owner=user).select_related(*RELATED)


def caregiver_bookings(user):
    """Booking requests sent to the signed-in user's caregiver profile."""
    return Booking.objects.filter(caregiver__user=user).select_related(*RELATED)


@login_required
def booking_create(request):
    # Requesting care is the pet owner's side; caregivers answer requests instead.
    if getattr(request.user, "caregiver_profile", None):
        messages.info(
            request,
            "Caregiver accounts answer care requests. "
            "Use a pet owner account to request care.",
        )
        return redirect("bookings:caregiver_requests")

    if request.method == "POST":
        form = BookingRequestForm(request.POST, owner=request.user)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.owner = request.user
            booking.status = Booking.Status.PENDING
            booking.save()
            messages.success(
                request,
                f"Request sent to {booking.caregiver.name}. "
                "It stays Pending until they respond.",
            )
            return redirect(booking)
    else:
        # Pre-select a caregiver or pet when coming from their profile page.
        initial = {
            key: request.GET[key]
            for key in ("caregiver", "pet")
            if request.GET.get(key, "").isdigit()
        }
        form = BookingRequestForm(initial=initial, owner=request.user)
    return render(request, "bookings/booking_form.html", {"form": form})


@login_required
def booking_list(request):
    return render(
        request,
        "bookings/booking_list.html",
        {"bookings": owner_bookings(request.user)},
    )


@login_required
def booking_detail(request, pk):
    # Both the owner who sent the request and the caregiver it was sent to can see it.
    visible = Booking.objects.filter(
        Q(owner=request.user) | Q(caregiver__user=request.user)
    ).select_related(*RELATED)
    booking = get_object_or_404(visible, pk=pk)
    is_caregiver = booking.caregiver.user_id == request.user.pk
    return render(
        request,
        "bookings/booking_detail.html",
        {
            "booking": booking,
            "is_caregiver": is_caregiver,
            "can_respond": is_caregiver
            and booking.status == Booking.Status.PENDING
            and booking.start_time > timezone.now(),
        },
    )


# Tabs on the caregiver's "Care requests" page, in the order the design shows them.
REQUEST_TABS = [
    ("pending", "Pending"),
    ("accepted", "Accepted"),
    ("declined", "Declined"),
    ("all", "All"),
]


@login_required
def caregiver_requests(request):
    """Stories #74 and #76: the caregiver's care requests, one selected at a time."""
    profile = getattr(request.user, "caregiver_profile", None)
    if profile is None:
        return render(request, "bookings/caregiver_requests.html", {"profile": None})

    now = timezone.now()
    mine = caregiver_bookings(request.user)
    by_tab = {
        # Only requests that can still be answered count as Pending.
        "pending": mine.filter(status=Booking.Status.PENDING, start_time__gt=now),
        "accepted": mine.filter(status=Booking.Status.ACCEPTED),
        "declined": mine.filter(status=Booking.Status.DECLINED),
        "all": mine,
    }

    active = request.GET.get("status", "pending")
    if active not in by_tab:
        active = "pending"
    bookings = list(by_tab[active].order_by("start_time"))

    # The request shown in the side panel: ?b=<id> if it's in this tab, else the first.
    selected_id = request.GET.get("b", "")
    selected = next(
        (b for b in bookings if str(b.pk) == selected_id),
        bookings[0] if bookings else None,
    )

    return render(
        request,
        "bookings/caregiver_requests.html",
        {
            "profile": profile,
            "tabs": [
                {"key": key, "label": label, "count": by_tab[key].count()}
                for key, label in REQUEST_TABS
            ],
            "active_tab": active,
            "pending_count": by_tab["pending"].count(),
            "bookings": bookings,
            "selected": selected,
            "can_respond": bool(
                selected
                and selected.status == Booking.Status.PENDING
                and selected.start_time > now
            ),
            "upcoming": by_tab["accepted"]
            .filter(end_time__gt=now)
            .order_by("start_time")[:4],
        },
    )

@login_required
def caregiver_commitments(request):
    profile = getattr(request.user, "caregiver_profile", None)

    if profile is None:
        return redirect("create_caregiver_profile")

    now = timezone.now()

    accepted = caregiver_bookings(request.user).filter(
        status=Booking.Status.ACCEPTED
    )

    upcoming = accepted.filter(
        start_time__gt=now
    ).order_by("start_time")

    in_progress = accepted.filter(
        start_time__lte=now,
        end_time__gt=now
    ).order_by("end_time")

    past = accepted.filter(
        end_time__lte=now
    ).order_by("-start_time")

    return render(
        request,
        "bookings/caregiver_commitments.html",
        {
            "upcoming": upcoming,
            "in_progress": in_progress,
            "past": past,
        }
    )
def owner_name(user):
    """A user's name as "Kat W.", falling back to their username."""
    first, last = user.first_name.strip(), user.last_name.strip()
    if first and last:
        return f"{first} {last[0]}."
    return first or user.username


def response_message(booking, new_status):
    """Confirmation shown to the caregiver after they accept or decline."""
    when = dateformat.format(
        timezone.localtime(booking.start_time), r"D, M j \a\t g:i A"
    )
    details = f"{booking.pet.name} · {booking.service_type.name} on {when}"
    owner = owner_name(booking.owner)
    if new_status == Booking.Status.ACCEPTED:
        return (
            f"Request accepted: {details}. {owner} will see it as Accepted, "
            "and it's now in your upcoming care."
        )
    return f"Request declined: {details}. {owner} will see it as Declined."


@login_required
@require_POST
def booking_respond(request, pk):
    """Story #76: the caregiver accepts or declines a Pending request."""
    action = request.POST.get("action")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
    if action not in ("accept", "decline"):
        return HttpResponseBadRequest("Unknown action.")
    booking = get_object_or_404(caregiver_bookings(request.user), pk=pk)

    if booking.status != Booking.Status.PENDING:
        messages.error(request, "This request has already been answered.")
        return redirect(next_url or booking)
    if booking.start_time <= timezone.now():
        messages.error(request, "This request's start time has passed.")
        return redirect(next_url or booking)

    with transaction.atomic():
        # Lock the caregiver row so two accepts can't both pass the overlap check.
        CaregiverProfile.objects.select_for_update().get(pk=booking.caregiver_id)
        if action == "accept":
            clash = (
                Booking.objects.filter(
                    caregiver_id=booking.caregiver_id,
                    status=Booking.Status.ACCEPTED,
                    start_time__lt=booking.end_time,
                    end_time__gt=booking.start_time,
                )
                .exclude(pk=booking.pk)
                .exists()
            )
            if clash:
                messages.error(
                    request,
                    "You already accepted a booking that overlaps this time.",
                )
                return redirect(next_url or booking)
            new_status = Booking.Status.ACCEPTED
        else:
            new_status = Booking.Status.DECLINED

        # Only change it if it's still Pending (guards against double submits).
        updated = Booking.objects.filter(
            pk=booking.pk, status=Booking.Status.PENDING
        ).update(status=new_status, updated_at=timezone.now())

    if not updated:
        messages.error(request, "This request has already been answered.")
    else:
        messages.success(request, response_message(booking, new_status))
    return redirect(next_url or booking)
