from django.urls import path

from . import admin_views, views

app_name = "reports"

urlpatterns = [
    path("review/<int:pk>/", views.report_review, name="review"),
    path("message/<int:pk>/", views.report_message, name="message"),
    # Admin pages (#95).
    path("admin/", admin_views.report_list, name="admin_list"),
    path("admin/<int:pk>/", admin_views.report_detail, name="admin_detail"),
]
