from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from bookings.models import Booking

from .forms import PetForm
from .models import Pet


class OwnerPetsMixin(LoginRequiredMixin):
    """Limit every pet query to the logged-in owner's own pets."""

    def get_queryset(self):
        return Pet.objects.filter(owner=self.request.user).select_related("pet_type")


class PetListView(OwnerPetsMixin, ListView):
    model = Pet
    template_name = "pets/pet_list.html"
    context_object_name = "pets"

    def get_queryset(self):
        # Newest first, so a just-created pet appears at the top.
        return super().get_queryset().order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        new_pet = self.request.GET.get("new", "")
        context["new_pet_id"] = int(new_pet) if new_pet.isdigit() else None
        return context


class PetDetailView(OwnerPetsMixin, DetailView):
    model = Pet
    template_name = "pets/pet_detail.html"
    context_object_name = "pet"


class PetCreateView(LoginRequiredMixin, CreateView):
    model = Pet
    form_class = PetForm
    template_name = "pets/pet_form.html"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"{self.object.name}'s profile was created.")
        return response

    def get_success_url(self):
        return f"{reverse('pets:list')}?new={self.object.pk}"


class PetUpdateView(OwnerPetsMixin, UpdateView):
    model = Pet
    form_class = PetForm
    template_name = "pets/pet_form.html"
    context_object_name = "pet"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"{self.object.name}'s profile was updated.")
        return response


def current_care(user):
    """Accepted bookings for this caregiver that haven't ended yet."""
    return Booking.objects.filter(
        caregiver__user=user,
        status=Booking.Status.ACCEPTED,
        end_time__gt=timezone.now(),
    )


class CaregiverPetView(LoginRequiredMixin, DetailView):
    """
    Stories #84-#88: a caregiver's read-only view of a pet, with its feeding,
    medication and emergency information. Only available while the caregiver
    has an accepted booking for the pet that hasn't ended.
    """

    model = Pet
    template_name = "pets/pet_care_view.html"
    context_object_name = "pet"

    def get(self, request, *args, **kwargs):
        # Owners already have their own page for their pet.
        if Pet.objects.filter(pk=kwargs["pk"], owner=request.user).exists():
            return redirect("pets:detail", pk=kwargs["pk"])
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        pet_ids = current_care(self.request.user).values("pet_id")
        return Pet.objects.filter(pk__in=pet_ids).select_related("pet_type", "owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["care_bookings"] = (
            current_care(self.request.user)
            .filter(pet=self.object)
            .select_related("service_type")
            .order_by("start_time")
        )
        # Emergency and vet contacts only while one of these bookings is happening.
        context["show_contacts"] = (
            context["care_bookings"].filter(start_time__lte=timezone.now()).exists()
        )
        return context
