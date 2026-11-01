from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("booking", "author", "role", "rating", "created_at")
    list_filter = ("role", "rating")
