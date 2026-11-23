from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/restrict/", views.restrict_user, name="restrict_user"),
    path("users/<int:pk>/reinstate/", views.reinstate_user, name="reinstate_user"),
    # #103: restrict or restore forum posting only.
    path("users/<int:pk>/forum/restrict/", views.restrict_forum, name="restrict_forum"),
    path("users/<int:pk>/forum/restore/", views.restore_forum, name="restore_forum"),
    # #93: an admin deletes an account.
    path("users/<int:pk>/delete/", views.delete_user, name="delete_user"),
    # #99: remove a review from the account's review history.
    path(
        "users/<int:pk>/reviews/<int:review_pk>/remove/",
        views.remove_review,
        name="remove_review",
    ),
    path(
        "types/",
        views.manage_types,
        name="manage_types",
    ),
    path(
        "types/rename/",
        views.rename_type,
        name="rename_type",
    ),
    path(
        "types/add/",
        views.add_type,
        name="add_type",
    ),
]
