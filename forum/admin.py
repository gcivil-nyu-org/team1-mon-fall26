from django.contrib import admin

from .models import Comment, GuidelineRule, Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at", "removed_at")
    list_filter = ("topic", "removed_at")
    search_fields = ("title", "body", "author__username")
    readonly_fields = ("created_at",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author", "created_at", "removed_at")
    list_filter = ("removed_at",)
    search_fields = ("body", "author__username", "post__title")
    readonly_fields = ("created_at",)


@admin.register(GuidelineRule)
class GuidelineRuleAdmin(admin.ModelAdmin):
    list_display = ("title", "position", "updated_at", "removed_at")
    list_filter = ("removed_at",)
    search_fields = ("title", "text")
    readonly_fields = ("updated_at",)
