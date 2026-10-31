from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("booking/<int:booking_pk>/", views.review_create, name="create"),
    path("<int:pk>/thanks/", views.review_thanks, name="thanks"),
]
