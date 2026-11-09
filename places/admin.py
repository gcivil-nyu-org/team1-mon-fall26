from django.contrib import admin

from .models import Place, PlaceReport


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "borough", "source", "checked_on", "is_active")
    list_filter = ("category", "source", "borough", "is_active")
    search_fields = ("name", "address", "neighborhood", "zip_code")
    readonly_fields = ("source_id", "created_at", "updated_at")


@admin.register(PlaceReport)
class PlaceReportAdmin(admin.ModelAdmin):
    list_display = ("place", "reporter", "created_at", "is_resolved")
    list_filter = ("is_resolved",)
    search_fields = ("place__name", "details", "reporter__username")
    list_editable = ("is_resolved",)
