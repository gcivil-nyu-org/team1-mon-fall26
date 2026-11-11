from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/restrict/", views.restrict_user, name="restrict_user"),
    path("users/<int:pk>/reinstate/", views.reinstate_user, name="reinstate_user"),
    # #99: remove a review from the account's review history.
    path(
        "users/<int:pk>/reviews/<int:review_pk>/remove/",
        views.remove_review,
        name="remove_review",
    ),
]
