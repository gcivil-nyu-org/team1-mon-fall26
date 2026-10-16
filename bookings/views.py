from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BookingRequestForm
from .models import Booking


def _visible_bookings(request):
    """Bookings the current visitor is allowed to see.

    Signed-in users see only their own bookings. Until account sign-up is
    built, anonymous visitors see only bookings created without an owner.
    """
    bookings = Booking.objects.select_related("pet", "caregiver", "service_type")
    if request.user.is_authenticated:
        return bookings.filter(owner=request.user)
    return bookings.filter(owner__isnull=True)


def booking_create(request):
    if request.method == "POST":
        form = BookingRequestForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.status = Booking.Status.PENDING
            if request.user.is_authenticated:
                booking.owner = request.user
            booking.save()
            messages.success(request, "Booking request sent. Status: Pending.")
            return redirect("bookings:booking_detail", pk=booking.pk)
    else:
        initial = {}
        if request.GET.get("caregiver"):
            initial["caregiver"] = request.GET["caregiver"]
        if request.GET.get("pet"):
            initial["pet"] = request.GET["pet"]
        form = BookingRequestForm(initial=initial)
    return render(request, "bookings/booking_form.html", {"form": form})


def booking_list(request):
    return render(
        request, "bookings/booking_list.html", {"bookings": _visible_bookings(request)}
    )


def booking_detail(request, pk):
    booking = get_object_or_404(_visible_bookings(request), pk=pk)
    return render(request, "bookings/booking_detail.html", {"booking": booking})
