from django.urls import path

from . import views

app_name = "forum"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("new/", views.post_create, name="create"),
    path("<int:pk>/", views.post_detail, name="detail"),
    path("<int:pk>/comments/", views.add_comment, name="comment"),
]
