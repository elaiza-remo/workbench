from django.urls import path

from . import views

app_name = "prep"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("stories/", views.story_list, name="story_list"),
    path("stories/new/", views.story_form, name="story_create"),
    path("stories/<int:pk>/", views.story_detail, name="story_detail"),
    path("stories/<int:pk>/edit/", views.story_form, name="story_update"),
    path("stories/<int:pk>/delete/", views.story_delete, name="story_delete"),

    path("questions/", views.question_list, name="question_list"),
    path("questions/new/", views.question_form, name="question_create"),
    path("questions/import/", views.question_import, name="question_import"),
    path("questions/<int:pk>/seen/", views.question_add_sighting, name="question_add_sighting"),
    path("sightings/<int:pk>/delete/", views.sighting_delete, name="sighting_delete"),
    path("questions/<int:pk>/", views.question_detail, name="question_detail"),
    path("questions/<int:pk>/edit/", views.question_form, name="question_update"),
    path("questions/<int:pk>/delete/", views.question_delete, name="question_delete"),

    path("projects/", views.project_list, name="project_list"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),

    path("practice/", views.practice, name="practice"),
    path("practice/<int:pk>/rate/", views.practice_rate, name="practice_rate"),
    path("practice/<int:pk>/feedback/", views.practice_feedback, name="practice_feedback"),
    path("history/", views.history, name="history"),
]
