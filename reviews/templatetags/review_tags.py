from django import template

from ..models import Review, rating_summary

register = template.Library()


@register.inclusion_tag("reviews/partials/booking_review_box.html", takes_context=True)
def booking_review_box(context, booking):
    """On a completed booking: the viewer's review, or a button to leave one."""
    user = context["request"].user
    mine = None
    if user.is_authenticated:
        mine = Review.objects.filter(booking=booking, author=user).first()
    return {
        "booking": booking,
        "review": mine,
        "can_review": booking.status == "completed" and mine is None,
        "is_caregiver": booking.caregiver.user_id == user.pk,
    }


@register.inclusion_tag("reviews/partials/review_list.html")
def caregiver_reviews(caregiver):
    """Owners' ratings and reviews of this caregiver (#62, #63)."""
    reviews = Review.objects.filter(
        booking__caregiver=caregiver, role=Review.Role.OWNER
    ).select_related("author", "booking__pet", "booking__service_type")
    return {
        "reviews": reviews,
        "summary": rating_summary(reviews),
        "title": "Reviews",
        "empty": f"{caregiver.name} has no reviews yet.",
        "show": "pet",
    }


@register.inclusion_tag("reviews/partials/review_list.html")
def pet_reviews(pet):
    """Caregivers' ratings and reviews of this owner and pet (#66)."""
    reviews = Review.objects.filter(
        booking__pet=pet, role=Review.Role.CAREGIVER
    ).select_related("author", "booking__caregiver", "booking__service_type")
    return {
        "reviews": reviews,
        "summary": rating_summary(reviews),
        "title": "Notes from caregivers",
        "empty": f"No caregiver has reviewed {pet.name} yet.",
        "show": "caregiver",
    }


@register.inclusion_tag("reviews/partials/paws.html")
def paws(rating, size="small"):
    """Five paws with the first `rating` filled in (Figma uses paws, not stars)."""
    rating = int(round(rating or 0))
    return {
        "rating": rating,
        "filled": range(rating),
        "empty": range(5 - rating),
        "size": size,
    }


@register.filter
def avatar_tone(user):
    """Gives each reviewer one of three avatar colours, like the Figma (yellow, blue, pink)."""
    return user.pk % 3


@register.filter
def initials(user):
    """ "Kat Wong" -> "KW"; falls back to the first two letters of the username."""
    first, last = user.first_name.strip(), user.last_name.strip()
    if first and last:
        return f"{first[0]}{last[0]}".upper()
    return (first or user.username)[:2].upper()


@register.filter
def reviewer_name(user):
    """ "Kat Wong" -> "Kat W."; falls back to the username."""
    first, last = user.first_name.strip(), user.last_name.strip()
    if first and last:
        return f"{first} {last[0]}."
    return first or user.username


@register.filter
def owner_can_rate(booking):
    """For the owner's booking panel: a completed visit the owner hasn't rated yet.

    The panel only lists the owner's own bookings, so the owner is the viewer.
    """
    return (
        booking.status == "completed"
        and not Review.objects.filter(
            booking=booking, author_id=booking.owner_id
        ).exists()
    )


@register.inclusion_tag("reviews/partials/pet_rating_line.html")
def pet_rating_line(pet):
    """One line for the request panel: how earlier caregivers rated this owner and pet."""
    reviews = Review.objects.filter(booking__pet=pet, role=Review.Role.CAREGIVER)
    return {"pet": pet, "summary": rating_summary(reviews), "latest": reviews.first()}
