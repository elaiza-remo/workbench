import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prep", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="text",
            field=models.CharField(max_length=500, unique=True),
        ),
        migrations.CreateModel(
            name="QuestionSighting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("interview", "Asked in an interview"), ("application", "On a job application"), ("other", "Somewhere else")], default="interview", max_length=20)),
                ("company", models.CharField(blank=True, max_length=120)),
                ("seen_on", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sightings", to="prep.question")),
            ],
            options={"ordering": ["-seen_on", "-created_at"]},
        ),
    ]
