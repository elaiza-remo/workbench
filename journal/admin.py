from django.contrib import admin

from .models import Commit, Note


@admin.register(Commit)
class CommitAdmin(admin.ModelAdmin):
    list_display = ["short_sha", "subject", "project", "committed_at"]
    list_filter = ["project"]
    search_fields = ["sha", "message"]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "project", "happened_on"]
    list_filter = ["kind", "project"]
    search_fields = ["title", "context", "details", "outcome"]
    filter_horizontal = ["commits", "tags", "stories"]
