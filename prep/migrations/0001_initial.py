import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Story",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("situation", models.TextField(blank=True, help_text="Where were you and what was going on?")),
                ("task", models.TextField(blank=True, help_text="What were you responsible for?")),
                ("action", models.TextField(blank=True, help_text="What did you specifically do?")),
                ("result", models.TextField(blank=True, help_text="What happened? Use numbers if you can.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stories", to="prep.project")),
                ("tags", models.ManyToManyField(blank=True, related_name="stories", to="prep.tag")),
            ],
            options={"ordering": ["-updated_at"], "verbose_name_plural": "stories"},
        ),
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=300, unique=True)),
                ("category", models.CharField(choices=[("behavioral", "Behavioural"), ("technical", "Technical"), ("general", "General")], default="behavioral", max_length=20)),
                ("notes", models.TextField(blank=True, help_text="Talking points, reminders, things to avoid.")),
                ("ease", models.FloatField(default=2.5)),
                ("interval_days", models.PositiveIntegerField(default=0)),
                ("repetitions", models.PositiveIntegerField(default=0)),
                ("due_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("stories", models.ManyToManyField(blank=True, related_name="questions", to="prep.story")),
                ("tags", models.ManyToManyField(blank=True, related_name="questions", to="prep.tag")),
            ],
            options={"ordering": ["text"]},
        ),
        migrations.CreateModel(
            name="PracticeAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField(choices=[(1, "Again — blanked or rambled"), (2, "Hard — got there, but shaky"), (3, "Good — solid answer"), (4, "Easy — nailed it")])),
                ("duration_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("answer_text", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("ai_feedback", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="prep.question")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
