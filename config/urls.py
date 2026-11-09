"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import home_view

urlpatterns = [
    # The welcome page (templates/home.html) isn't in the Figma design, so "/" sends
    # people straight to their start page instead.
    path("", home_view, name="home"),
    path("admin/", admin.site.urls),
    path("caregivers/", include("caregivers.urls")),
    path("pets/", include("pets.urls")),
    path("bookings/", include("bookings.urls")),
    path("reviews/", include("reviews.urls")),
    path("accounts/", include("accounts.urls")),
    path("messages/", include("messaging.urls")),
    path("opportunities/", include("opportunities.urls")),
    # Admin pages for PawPal accounts (#89-#92); Django's own admin stays at /admin/.
    path("manage/", include("staff.urls")),
    path("reports/", include("reports.urls")),
    path("explore/", include("places.urls")),
]

# Serve uploaded photos while developing locally.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
