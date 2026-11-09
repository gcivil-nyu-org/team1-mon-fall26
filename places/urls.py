from django.urls import path

from . import views

app_name = "places"

urlpatterns = [
    path("places/", views.explore_places, name="explore"),
    path("places/<int:pk>/report/", views.report_place, name="report"),
]
