from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
]
