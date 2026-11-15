from django.contrib import admin

from .models import Place, PlaceReport


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "borough", "source", "checked_on", "is_active")
    # Admins normally use the "Pet-friendly places" page (Explore in the admin
    # header); this is the Django admin fallback.
    list_filter = ("category", "source", "borough", "is_active")
    search_fields = ("name", "address", "neighborhood", "zip_code")
    readonly_fields = ("source_id", "created_at", "updated_at", "edited_at")


@admin.register(PlaceReport)
class PlaceReportAdmin(admin.ModelAdmin):
    list_display = ("place", "reason", "reporter", "created_at", "status")
    list_filter = ("status", "reason")
    search_fields = ("place__name", "details", "reporter__username")
    readonly_fields = ("resolved_by", "resolved_at")
