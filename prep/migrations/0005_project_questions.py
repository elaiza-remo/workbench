import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prep", "0004_project_details"),
        ("journal", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="category",
            field=models.CharField(choices=[("behavioral", "Behavioural"), ("technical", "Technical"), ("general", "General"), ("project", "Project deep-dive")], default="behavioral", max_length=20),
        ),
        migrations.AddField(
            model_name="question",
            name="project",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="practice_questions", to="prep.project"),
        ),
        migrations.AddField(
            model_name="question",
            name="source_note",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="practice_questions", to="journal.note"),
        ),
    ]
