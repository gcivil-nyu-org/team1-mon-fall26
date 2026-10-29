from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from bookings.models import Booking

from .forms import ReviewForm
from .models import Review


@login_required
def review_create(request, booking_pk):
    """Stories #62, #63 and #66: rate and review a completed booking, once."""
    visible = Booking.objects.filter(
        Q(owner=request.user) | Q(caregiver__user=request.user)
    ).select_related("owner", "pet", "caregiver", "service_type")
    booking = get_object_or_404(visible, pk=booking_pk)
    role = Review.role_for(request.user, booking)
    if role is None:  # pragma: no cover - the queryset above already limits this
        raise Http404

    if booking.status != Booking.Status.COMPLETED:
        messages.error(request, "You can leave a review once the booking is completed.")
        return redirect(booking)
    if Review.objects.filter(booking=booking, author=request.user).exists():
        messages.info(request, "You've already reviewed this booking.")
        return redirect(booking)

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            review.author = request.user
            review.role = role
            review.save()
            messages.success(request, "Thanks! Your review was saved.")
            return redirect(booking)
    else:
        form = ReviewForm()

    is_caregiver = role == Review.Role.CAREGIVER
    form.fields["comment"].widget.attrs["placeholder"] = (
        f"How was caring for {booking.pet.name}? Anything other caregivers should know?"
        if is_caregiver
        else f"How did {booking.caregiver.name} do with {booking.pet.name}?"
    )
    return render(
        request,
        "reviews/review_form.html",
        {"form": form, "booking": booking, "is_caregiver": is_caregiver},
    )
