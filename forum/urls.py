from django.urls import path

from . import views

app_name = "forum"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("new/", views.post_create, name="create"),
    path("<int:pk>/", views.post_detail, name="detail"),
    path("<int:pk>/comments/", views.add_comment, name="comment"),
    # #102: admins remove spam or abusive posts and comments.
    path("<int:pk>/remove/", views.remove_post, name="remove_post"),
    path("comments/<int:pk>/remove/", views.remove_comment, name="remove_comment"),
    # #104: admins pin helpful posts to the top of the forum.
    path("<int:pk>/pin/", views.pin_post, name="pin_post"),
    path("<int:pk>/unpin/", views.unpin_post, name="unpin_post"),
]
