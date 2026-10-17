from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

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
