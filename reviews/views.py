from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from bookings.models import Booking

from .forms import MAX_REVIEW_LENGTH, ReviewForm
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
            return redirect("reviews:thanks", pk=review.pk)
    else:
        form = ReviewForm()

    is_caregiver = role == Review.Role.CAREGIVER
    owner_first = booking.owner.first_name or booking.owner.username
    caregiver_first = booking.caregiver.name.split()[0]
    form.fields["comment"].widget.attrs["placeholder"] = (
        f"How was {booking.pet.name}? Was {owner_first} easy to work with?"
        if is_caregiver
        else f"What went well? Anything {caregiver_first} could do better?"
    )
    return render(
        request,
        "reviews/review_form.html",
        {
            "form": form,
            "booking": booking,
            "is_caregiver": is_caregiver,
            "heading": (
                f"How were {booking.pet.name} and {owner_first}?"
                if is_caregiver
                else f"How was {caregiver_first}?"
            ),
            "back_url": back_url(is_caregiver),
            "max_length": MAX_REVIEW_LENGTH,
        },
    )


@login_required
def review_thanks(request, pk):
    """Figma "Thanks" screen: shows the review you just left."""
    review = get_object_or_404(
        Review.objects.select_related(
            "author",
            "booking__pet",
            "booking__service_type",
            "booking__caregiver",
            "booking__owner",
        ),
        pk=pk,
        author=request.user,
    )
    return render(
        request,
        "reviews/review_thanks.html",
        {
            "review": review,
            "booking": review.booking,
            "is_caregiver": review.role == Review.Role.CAREGIVER,
            "back_url": back_url(review.role == Review.Role.CAREGIVER),
        },
    )


def back_url(is_caregiver):
    return reverse(
        "bookings:caregiver_requests" if is_caregiver else "bookings:booking_list"
    )
