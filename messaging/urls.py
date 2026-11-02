from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("", views.inbox_view, name="inbox"),
    path("<int:pk>/", views.conversation_view, name="conversation"),
    path("<int:pk>/send/", views.send_message, name="send"),
    path("<int:pk>/latest/", views.latest_message, name="latest"),
    path(
        "caregiver/<int:caregiver_pk>/",
        views.message_caregiver,
        name="message_caregiver",
    ),
    path(
        "booking/<int:booking_pk>/",
        views.message_about_booking,
        name="message_booking",
    ),
]
