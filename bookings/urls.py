from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("", views.booking_list, name="booking_list"),
    path("new/", views.booking_create, name="booking_create"),
    path("incoming/", views.caregiver_requests, name="caregiver_requests"),
    path("<int:pk>/", views.booking_detail, name="booking_detail"),
    path("<int:pk>/respond/", views.booking_respond, name="booking_respond"),
    path("<int:pk>/cancel/", views.booking_cancel, name="booking_cancel"),
    path("<int:pk>/complete/", views.booking_complete, name="booking_complete"),
]
