from django.urls import path

from . import admin_views, views

app_name = "reports"

urlpatterns = [
    path("review/<int:pk>/", views.report_review, name="review"),
    path("message/<int:pk>/", views.report_message, name="message"),
    # Admin pages (#95, #98).
    path("admin/", admin_views.report_list, name="admin_list"),
    path("admin/<int:pk>/", admin_views.report_detail, name="admin_detail"),
    path("admin/<int:pk>/dismiss/", admin_views.report_dismiss, name="admin_dismiss"),
]
