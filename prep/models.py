from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.ownership import OwnedQuerySet, owner_field


class Tag(models.Model):
    """A theme like 'conflict', 'leadership', or 'failure'."""

    owner = owner_field()
    name = models.CharField(max_length=50)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_tag_per_owner")]

    def __str__(self):
        return self.name


class Project(models.Model):
    """Something you built or worked on. Shared by the story bank and the project journal."""

    ACTIVE, PAUSED, FINISHED = "active", "paused", "finished"
    STATUS_CHOICES = [(ACTIVE, "Active"), (PAUSED, "Paused"), (FINISHED, "Finished")]

    owner = owner_field()
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    tech_stack = models.CharField(max_length=200, blank=True, help_text="e.g. Django, React, PostgreSQL")
    repo_path = models.CharField(
        "Repo folder", max_length=500, blank=True,
        help_text="Optional. Only used when Workbench runs on your own computer, e.g. ~/code/efit.",
    )
    repo_url = models.URLField(
        "GitHub repo link", blank=True,
        help_text="e.g. https://github.com/you/project. Commits are imported from here.",
    )
    started_on = models.DateField(null=True, blank=True)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_project_per_owner", violation_error_message="You already have a project with this name.")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("journal:project_detail", args=[self.pk])

    def commit_url(self, sha):
        """Link to a commit on GitHub/GitLab when the repo link is set."""
        if not self.repo_url:
            return ""
        return f"{self.repo_url.rstrip('/').removesuffix('.git')}/commit/{sha}"


class Story(models.Model):
    """A behavioural answer written in STAR format."""

    owner = owner_field()
    title = models.CharField(max_length=200)
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="stories"
    )
    situation = models.TextField(blank=True, help_text="Where were you and what was going on?")
    task = models.TextField(blank=True, help_text="What were you responsible for?")
    action = models.TextField(blank=True, help_text="What did you specifically do?")
    result = models.TextField(blank=True, help_text="What happened? Use numbers if you can.")
    brainstorm = models.TextField(blank=True, help_text="Rough notes. Only you see these.")
    tags = models.ManyToManyField(Tag, blank=True, related_name="stories")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    STAR_FIELDS = ("situation", "task", "action", "result")

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "stories"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("prep:story_detail", args=[self.pk])

    @property
    def missing_parts(self):
        return [f for f in self.STAR_FIELDS if not getattr(self, f).strip()]

    @property
    def is_complete(self):
        return not self.missing_parts


class Question(models.Model):
    """An interview question, plus its spaced-repetition schedule."""

    BEHAVIORAL = "behavioral"
    TECHNICAL = "technical"
    GENERAL = "general"
    PROJECT = "project"
    CATEGORY_CHOICES = [
        (BEHAVIORAL, "Behavioural"),
        (TECHNICAL, "Technical"),
        (GENERAL, "General"),
        (PROJECT, "Project deep-dive"),
    ]

    owner = owner_field()
    text = models.CharField(max_length=500)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=BEHAVIORAL)
    tags = models.ManyToManyField(Tag, blank=True, related_name="questions")
    stories = models.ManyToManyField(Story, blank=True, related_name="questions")
    notes = models.TextField(blank=True, help_text="Talking points, reminders, things to avoid.")
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="practice_questions"
    )
    source_note = models.ForeignKey(
        "journal.Note", null=True, blank=True, on_delete=models.SET_NULL, related_name="practice_questions"
    )

    # Spaced repetition (a simplified SM-2): see prep/srs.py
    ease = models.FloatField(default=2.5)
    interval_days = models.PositiveIntegerField(default=0)
    repetitions = models.PositiveIntegerField(default=0)
    due_at = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["text"]
        constraints = [models.UniqueConstraint(fields=["owner", "text"], name="unique_question_per_owner", violation_error_message="This question is already in your library.")]

    def __str__(self):
        return self.text

    def get_absolute_url(self):
        return reverse("prep:question_detail", args=[self.pk])

    @property
    def is_due(self):
        return self.due_at <= timezone.now()

    @property
    def companies(self):
        """Distinct companies this was seen at, in the order first logged.

        Uses prefetched sightings when available, so list pages stay to one query.
        """
        names = []
        for s in sorted(self.sightings.all(), key=lambda s: s.created_at):
            if s.company and s.company.lower() not in (n.lower() for n in names):
                names.append(s.company)
        return names


class QuestionSighting(models.Model):
    """A time you came across a question: in an interview or on an application."""

    INTERVIEW = "interview"
    APPLICATION = "application"
    OTHER = "other"
    SOURCE_CHOICES = [
        (INTERVIEW, "Asked in an interview"),
        (APPLICATION, "On a job application"),
        (OTHER, "Somewhere else"),
    ]

    OWNER_LOOKUP = "question__owner"

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="sightings")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=INTERVIEW)
    company = models.CharField(max_length=120, blank=True)
    seen_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["-seen_on", "-created_at"]

    def __str__(self):
        where = f" at {self.company}" if self.company else ""
        return f"{self.get_source_display()}{where}"

    @property
    def source_short(self):
        return {"interview": "Interview", "application": "Application"}.get(self.source, "Other")


class PracticeAttempt(models.Model):
    """One run at a question in practice mode."""

    AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
    RATING_CHOICES = [
        (AGAIN, "Again — blanked or rambled"),
        (HARD, "Hard — got there, but shaky"),
        (GOOD, "Good — solid answer"),
        (EASY, "Easy — nailed it"),
    ]

    OWNER_LOOKUP = "question__owner"

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="attempts")
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    answer_text = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    ai_feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.question} — {self.get_rating_display()}"

    @property
    def rating_short(self):
        return {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}.get(self.rating, "")

    @property
    def duration_display(self):
        if self.duration_seconds is None:
            return "—"
        m, s = divmod(self.duration_seconds, 60)
        return f"{m}:{s:02d}"
