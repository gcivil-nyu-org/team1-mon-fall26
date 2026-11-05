from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "kind",
        "reason",
        "reporter",
        "reported_user",
        "status",
    )
    list_filter = ("status", "kind", "reason")
    search_fields = ("reporter__username", "reported_user__username", "content_text")
    readonly_fields = ("created_at",)
