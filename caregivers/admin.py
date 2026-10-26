from django.contrib import admin

from .models import CaregiverProfile, CaregiverService, ServiceType


@admin.register(CaregiverProfile)
class CaregiverProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "service_area", "accepting_new_bookings")
    search_fields = ("name", "user__username")


admin.site.register(ServiceType)
admin.site.register(CaregiverService)
