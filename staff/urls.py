from django.urls import path

from . import place_views, views

app_name = "staff"

urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/restrict/", views.restrict_user, name="restrict_user"),
    path("users/<int:pk>/reinstate/", views.reinstate_user, name="reinstate_user"),
    # #93: an admin deletes an account.
    path("users/<int:pk>/delete/", views.delete_user, name="delete_user"),
    # #99: remove a review from the account's review history.
    path(
        "users/<int:pk>/reviews/<int:review_pk>/remove/",
        views.remove_review,
        name="remove_review",
    ),
    # #107: pet-friendly places, under Explore.
    path("places/", place_views.place_list, name="place_list"),
    path("places/<int:pk>/", place_views.place_detail, name="place_detail"),
    path("places/<int:pk>/hide/", place_views.hide_place, name="hide_place"),
    path("places/<int:pk>/show/", place_views.show_place, name="show_place"),
]
