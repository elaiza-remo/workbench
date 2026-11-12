from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prep", "0002_question_sightings"),
    ]

    operations = [
        migrations.AddField(
            model_name="story",
            name="brainstorm",
            field=models.TextField(blank=True, default="", help_text="Rough notes. Only you see these."),
            preserve_default=False,
        ),
    ]
