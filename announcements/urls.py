from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    # Admin pages.
    path("manage/", views.manage, name="manage"),
    path("manage/new/", views.create, name="create"),
    path("manage/<int:pk>/", views.detail, name="detail"),
    path("manage/<int:pk>/edit/", views.edit, name="edit"),
    path("manage/<int:pk>/publish/", views.publish, name="publish"),
    path("manage/<int:pk>/remove/", views.remove, name="remove"),
    # The × on the banner users see.
    path("<int:pk>/dismiss/", views.dismiss, name="dismiss"),
]
