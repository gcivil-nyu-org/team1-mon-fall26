from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "audience", "status", "published_at")
    list_filter = ("status", "kind", "audience")
    search_fields = ("title", "message")
