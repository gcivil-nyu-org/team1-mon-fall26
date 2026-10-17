from django.contrib import admin

from .models import Pet, PetType


@admin.register(Pet)
class PetAdmin(admin.ModelAdmin):
    list_display = ("name", "pet_type", "breed", "owner", "created_at")
    list_filter = ("pet_type",)
    search_fields = ("name", "breed", "owner__username")


@admin.register(PetType)
class PetTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
