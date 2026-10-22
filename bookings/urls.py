from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("", views.booking_list, name="booking_list"),
    path("new/", views.booking_create, name="booking_create"),
    path("incoming/", views.caregiver_requests, name="caregiver_requests"),
    path("<int:pk>/", views.booking_detail, name="booking_detail"),
    path("<int:pk>/respond/", views.booking_respond, name="booking_respond"),
    path(
    "commitments/",views.caregiver_commitments,name="caregiver_commitments"),
]
