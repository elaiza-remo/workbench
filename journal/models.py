from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.ownership import OwnedQuerySet
from prep.models import Project, Story, Tag


class Commit(models.Model):
    """A git commit imported from a project's repo (local folder or GitHub)."""

    OWNER_LOOKUP = "project__owner"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="commits")
    sha = models.CharField(max_length=40)
    message = models.TextField()
    author = models.CharField(max_length=200, blank=True)
    committed_at = models.DateTimeField()
    files_changed = models.PositiveIntegerField(default=0)
    insertions = models.PositiveIntegerField(default=0)
    deletions = models.PositiveIntegerField(default=0)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["-committed_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["project", "sha"], name="unique_commit_per_project")]

    def __str__(self):
        return f"{self.short_sha} {self.subject}"

    def get_absolute_url(self):
        return reverse("journal:commit_detail", args=[self.pk])

    @property
    def short_sha(self):
        return self.sha[:7]

    @property
    def subject(self):
        return self.message.split("\n", 1)[0]

    @property
    def body(self):
        parts = self.message.split("\n", 1)
        return parts[1].strip() if len(parts) > 1 else ""

    @property
    def remote_url(self):
        return self.project.commit_url(self.sha)


class Note(models.Model):
    """A journal entry about a project: a decision, an issue, AI use, a lesson…"""

    DECISION, ISSUE, AI, LEARNING, NOTE = "decision", "issue", "ai", "learning", "note"
    KIND_CHOICES = [
        (DECISION, "Decision"),
        (ISSUE, "Issue & fix"),
        (AI, "AI usage"),
        (LEARNING, "Learning"),
        (NOTE, "Note"),
    ]

    # Each kind of note uses the same three text fields, labelled to fit.
    FIELD_LABELS = {
        DECISION: {
            "context": ("The problem", "What were you trying to solve? Any constraints (time, team, tech)?"),
            "details": ("Options considered", "What else could you have done?"),
            "outcome": ("What you chose and why", "Your reasoning, and the trade-offs you accepted."),
        },
        ISSUE: {
            "context": ("What went wrong", "Symptoms, error messages, how you noticed."),
            "details": ("What you tried", "Dead ends count. They make good interview material."),
            "outcome": ("The fix", "What actually fixed it, and the root cause if you found it."),
        },
        AI: {
            "context": ("What you used it for", "The task or question you brought to the AI tool."),
            "details": ("What it gave you", "Code, an explanation, a plan, a review…"),
            "outcome": ("What you kept, changed or rejected", "How you checked its output and what you had to fix."),
        },
        LEARNING: {
            "context": ("What you learned", ""),
            "details": ("Where it came up", "The bug, feature or review that taught you this."),
            "outcome": ("How you'd use it next time", ""),
        },
        NOTE: {
            "context": ("Notes", ""),
            "details": ("More detail", ""),
            "outcome": ("Next steps", ""),
        },
    }
    TEXT_FIELDS = ("context", "details", "outcome")
    OWNER_LOOKUP = "project__owner"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=DECISION)
    title = models.CharField(max_length=200)
    context = models.TextField(blank=True)
    details = models.TextField(blank=True)
    outcome = models.TextField(blank=True)
    ai_tool = models.CharField("AI tool", max_length=80, blank=True, help_text="e.g. Claude, ChatGPT, Copilot")
    happened_on = models.DateField("Date", default=timezone.localdate)
    commits = models.ManyToManyField(Commit, blank=True, related_name="notes")
    tags = models.ManyToManyField(Tag, blank=True, related_name="project_notes")
    stories = models.ManyToManyField(Story, blank=True, related_name="source_notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OwnedQuerySet.as_manager()

    class Meta:
        ordering = ["-happened_on", "-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("journal:note_detail", args=[self.pk])

    def label_for(self, field):
        return self.FIELD_LABELS.get(self.kind, self.FIELD_LABELS[self.NOTE])[field][0]

    @property
    def sections(self):
        """[(label, text)] for the filled-in text fields, in order."""
        return [(self.label_for(f), getattr(self, f)) for f in self.TEXT_FIELDS if getattr(self, f).strip()]

    @property
    def preview(self):
        for f in self.TEXT_FIELDS:
            text = getattr(self, f).strip()
            if text:
                return text
        return ""

    def as_markdown(self, heading_level=3, include_project=False):
        h = "#" * heading_level
        d = self.happened_on
        meta = [self.get_kind_display(), f"{d:%b} {d.day}, {d.year}" if d else ""]
        if include_project:
            meta.insert(0, self.project.name)
        if self.kind == self.AI and self.ai_tool:
            meta.append(f"Tool: {self.ai_tool}")
        lines = [f"{h} {self.title}", "", "*" + " · ".join(m for m in meta if m) + "*", ""]
        for label, text in self.sections:
            lines += [f"**{label}**", "", text.strip(), ""]
        commits = list(self.commits.all())
        if commits:
            lines.append("**Commits:** " + ", ".join(f"`{c.short_sha}` {c.subject}" for c in commits))
            lines.append("")
        tags = [t.name for t in self.tags.all()]
        if tags:
            lines += ["**Tags:** " + ", ".join(tags), ""]
        return "\n".join(lines)
