from django.urls import path

from . import admin_views, views

app_name = "places"

urlpatterns = [
    path("places/", views.explore_places, name="explore"),
    path("places/<int:pk>/report/", views.report_place, name="report"),
    # Admin "Pet-friendly places" page (#107).
    path("places/manage/", admin_views.manage, name="manage"),
    path("places/manage/<int:pk>/", admin_views.manage_detail, name="manage_detail"),
    path("places/manage/<int:pk>/edit/", admin_views.edit, name="manage_edit"),
    path("places/manage/<int:pk>/hide/", admin_views.hide, name="manage_hide"),
    path("places/manage/<int:pk>/show/", admin_views.show, name="manage_show"),
]
