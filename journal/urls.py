from django.urls import path

from . import views

app_name = "journal"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("new/", views.project_form, name="project_create"),
    path("<int:pk>/", views.project_detail, name="project_detail"),
    path("<int:pk>/edit/", views.project_form, name="project_update"),
    path("<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("<int:pk>/sync/", views.project_sync, name="project_sync"),
    path("<int:pk>/questions/", views.project_questions, name="project_questions"),

    path("commits/<int:pk>/", views.commit_detail, name="commit_detail"),

    path("notes/", views.note_list, name="note_list"),
    path("notes/export/", views.note_export, name="note_export"),
    path("notes/new/", views.note_form, name="note_create"),
    path("notes/<int:pk>/", views.note_detail, name="note_detail"),
    path("notes/<int:pk>/edit/", views.note_form, name="note_update"),
    path("notes/<int:pk>/delete/", views.note_delete, name="note_delete"),
    path("notes/<int:pk>/to-story/", views.note_to_story, name="note_to_story"),
]
