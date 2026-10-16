from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "pet", "caregiver", "service_type", "start_time", "status")
    list_filter = ("status", "service_type")
