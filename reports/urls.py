from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("review/<int:pk>/", views.report_review, name="review"),
    path("message/<int:pk>/", views.report_message, name="message"),
]
