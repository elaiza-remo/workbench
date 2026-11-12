from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prep", "0003_story_brainstorm"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="status",
            field=models.CharField(choices=[("active", "Active"), ("paused", "Paused"), ("finished", "Finished")], default="active", max_length=20),
        ),
        migrations.AddField(
            model_name="project",
            name="tech_stack",
            field=models.CharField(blank=True, default="", help_text="e.g. Django, React, PostgreSQL", max_length=200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="project",
            name="repo_path",
            field=models.CharField(blank=True, default="", help_text="Folder on this computer with the git repo, e.g. ~/code/efit. Used to import commits.", max_length=500, verbose_name="Repo folder"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="project",
            name="repo_url",
            field=models.URLField(blank=True, default="", help_text="GitHub or GitLab link, optional.", verbose_name="Repo link"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="project",
            name="started_on",
            field=models.DateField(blank=True, null=True),
        ),
    ]
