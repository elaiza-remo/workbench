from django import forms

from prep.forms import OwnedFormMixin, TagsFieldMixin
from prep.models import Project

from .models import Commit, Note

DATE_INPUT = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ProjectForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "status", "description", "tech_stack", "started_on", "repo_path", "repo_url"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What is it, and who is it for?"}),
            "repo_path": forms.TextInput(attrs={"placeholder": "~/code/my-project"}),
            "repo_url": forms.URLInput(attrs={"placeholder": "https://github.com/you/my-project"}),
            "started_on": DATE_INPUT,
        }


class NoteForm(TagsFieldMixin):
    owned_choice_fields = ("project",)

    class Meta:
        model = Note
        fields = ["project", "kind", "title", "happened_on", "ai_tool", "context", "details", "outcome", "commits"]
        widgets = {
            "kind": forms.RadioSelect,
            "title": forms.TextInput(attrs={"placeholder": "e.g. Chose SQLite over Postgres for the MVP"}),
            "happened_on": DATE_INPUT,
            "ai_tool": forms.TextInput(attrs={"list": "ai-tools", "autocomplete": "off"}),
            "context": forms.Textarea(attrs={"rows": 4}),
            "details": forms.Textarea(attrs={"rows": 4}),
            "outcome": forms.Textarea(attrs={"rows": 4}),
            "commits": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = Note.KIND_CHOICES  # no blank "-----" option
        self.project_id = self._current_project_id()
        self.fields["commits"].queryset = (
            Commit.objects.for_user(self.owner).filter(project_id=self.project_id)
            if self.project_id else Commit.objects.none()
        )
        self.fields["commits"].label_from_instance = lambda c: f"{c.short_sha} · {c.subject}"
        self.fields["commits"].required = False

        # Label the three text fields for the current kind (the page script relabels on change).
        kind = self._current_kind()
        labels = Note.FIELD_LABELS.get(kind, Note.FIELD_LABELS[Note.NOTE])
        for name in Note.TEXT_FIELDS:
            self.fields[name].label, self.fields[name].help_text = labels[name]

    def _current_kind(self):
        if self.is_bound:
            return self.data.get("kind", Note.DECISION)
        if self.instance.pk:
            return self.instance.kind
        return self.initial.get("kind") or Note.DECISION

    def _current_project_id(self):
        if self.is_bound:
            value = self.data.get("project", "")
            return int(value) if str(value).isdigit() else None
        if self.instance.project_id:
            return self.instance.project_id
        initial = self.initial.get("project")
        return getattr(initial, "pk", initial)
