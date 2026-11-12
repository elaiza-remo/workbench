from django.contrib import admin

from .models import PracticeAttempt, Project, Question, QuestionSighting, Story, Tag


class SightingInline(admin.TabularInline):
    model = QuestionSighting
    extra = 0


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ["title", "project", "updated_at"]
    list_filter = ["project", "tags"]
    search_fields = ["title", "situation", "task", "action", "result", "brainstorm"]
    filter_horizontal = ["tags"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["text", "category", "due_at", "repetitions"]
    list_filter = ["category", "tags"]
    search_fields = ["text"]
    filter_horizontal = ["tags", "stories"]
    inlines = [SightingInline]


@admin.register(PracticeAttempt)
class PracticeAttemptAdmin(admin.ModelAdmin):
    list_display = ["question", "rating", "duration_seconds", "created_at"]
    list_filter = ["rating"]
