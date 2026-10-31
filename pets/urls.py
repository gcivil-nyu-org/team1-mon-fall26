from django.urls import path

from . import views

app_name = "pets"

urlpatterns = [
    path("", views.PetListView.as_view(), name="list"),
    path("new/", views.PetCreateView.as_view(), name="create"),
    path("<int:pk>/", views.PetDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.PetUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.PetDeleteView.as_view(), name="delete"),
    path("<int:pk>/care/", views.CaregiverPetView.as_view(), name="care_view"),
]
