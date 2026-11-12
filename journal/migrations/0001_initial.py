import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("prep", "0004_project_details"),
    ]

    operations = [
        migrations.CreateModel(
            name="Commit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sha", models.CharField(max_length=40)),
                ("message", models.TextField()),
                ("author", models.CharField(blank=True, max_length=200)),
                ("committed_at", models.DateTimeField()),
                ("files_changed", models.PositiveIntegerField(default=0)),
                ("insertions", models.PositiveIntegerField(default=0)),
                ("deletions", models.PositiveIntegerField(default=0)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commits", to="prep.project")),
            ],
            options={"ordering": ["-committed_at"]},
        ),
        migrations.AddConstraint(
            model_name="commit",
            constraint=models.UniqueConstraint(fields=("project", "sha"), name="unique_commit_per_project"),
        ),
        migrations.CreateModel(
            name="Note",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("decision", "Decision"), ("issue", "Issue & fix"), ("ai", "AI usage"), ("learning", "Learning"), ("note", "Note")], default="decision", max_length=20)),
                ("title", models.CharField(max_length=200)),
                ("context", models.TextField(blank=True)),
                ("details", models.TextField(blank=True)),
                ("outcome", models.TextField(blank=True)),
                ("ai_tool", models.CharField(blank=True, help_text="e.g. Claude, ChatGPT, Copilot", max_length=80, verbose_name="AI tool")),
                ("happened_on", models.DateField(default=django.utils.timezone.localdate, verbose_name="Date")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("commits", models.ManyToManyField(blank=True, related_name="notes", to="journal.commit")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notes", to="prep.project")),
                ("stories", models.ManyToManyField(blank=True, related_name="source_notes", to="prep.story")),
                ("tags", models.ManyToManyField(blank=True, related_name="project_notes", to="prep.tag")),
            ],
            options={"ordering": ["-happened_on", "-created_at"]},
        ),
    ]
