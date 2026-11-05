from django.urls import path

from . import views

app_name = "opportunities"

urlpatterns = [
    path("", views.opportunity_list, name="list"),
    path("new/", views.opportunity_create, name="create"),
    path("browse/", views.opportunity_browse, name="browse"),
    path("<int:pk>/created/", views.opportunity_created, name="created"),
    path("<int:pk>/edit/", views.opportunity_edit, name="edit"),
    path("<int:pk>/close/", views.opportunity_close, name="close"),
    path("<int:pk>/reopen/", views.opportunity_reopen, name="reopen"),
    path("<int:pk>/interest/", views.opportunity_interest, name="interest"),
    path("<int:pk>/withdraw-interest/", views.opportunity_withdraw_interest, name="withdraw_interest"),
]
