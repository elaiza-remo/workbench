from django import forms

from .models import PracticeAttempt, Project, Question, QuestionSighting, Story, Tag

DATE_INPUT = forms.DateInput(attrs={"type": "date"})
SOURCE_OPTIONAL_CHOICES = [("", "Don't log where I saw it")] + QuestionSighting.SOURCE_CHOICES


def parse_tags(text):
    """'Conflict, leadership,  conflict' -> ['conflict', 'leadership']"""
    seen = []
    for raw in text.split(","):
        name = raw.strip().lower()
        if name and name not in seen:
            seen.append(name[:50])
    return seen


class OwnedFormMixin:
    """For forms whose model has an owner (directly or through a parent).

    Pass `owner=request.user`. New objects are stamped with that owner, choice
    fields only offer that owner's objects, and per-owner uniqueness
    (e.g. two projects with the same name) is checked like any other field.
    """

    owned_choice_fields = ()

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        model = self._meta.model
        if owner is not None and any(f.name == "owner" for f in model._meta.fields) and not self.instance.owner_id:
            self.instance.owner = owner
        for name in self.owned_choice_fields:
            field = self.fields.get(name)
            if field is not None:
                field.queryset = field.queryset.model.objects.for_user(owner)

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude.discard("owner")
        return exclude


class TagsFieldMixin(OwnedFormMixin, forms.ModelForm):
    """Adds a comma-separated `tags_text` field that creates tags as needed."""

    tags_text = forms.CharField(
        label="Tags",
        required=False,
        help_text="Comma-separated, e.g. conflict, teamwork, deadline",
        widget=forms.TextInput(attrs={"list": "tag-suggestions", "autocomplete": "off"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["tags_text"].initial = ", ".join(t.name for t in self.instance.tags.all())

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit:
            self._save_tags(obj)
        else:
            original = self.save_m2m

            def save_m2m():
                original()
                self._save_tags(obj)

            self.save_m2m = save_m2m
        return obj

    def _save_tags(self, obj):
        names = parse_tags(self.cleaned_data.get("tags_text", ""))
        owner = self.owner or getattr(obj, "owner", None) or getattr(getattr(obj, "project", None), "owner", None)
        obj.tags.set([Tag.objects.get_or_create(owner=owner, name=n)[0] for n in names])


class OptionalPksField(forms.ModelMultipleChoiceField):
    """Multi-select that ignores blank values (e.g. an unused 'Choose…' dropdown)."""

    def clean(self, value):
        if value:
            value = [v for v in value if v not in ("", None)]
        return super().clean(value)


class StoryForm(TagsFieldMixin):
    new_project = forms.CharField(
        required=False,
        max_length=120,
        label="…or add a new project",
        help_text="Leave blank to use the project picked above.",
    )
    questions = OptionalPksField(queryset=Question.objects.all(), required=False)
    owned_choice_fields = ("project", "questions")

    class Meta:
        model = Story
        fields = ["title", "project", "situation", "task", "action", "result", "brainstorm"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Untangling a broken deploy the night before demo day"}),
            "situation": forms.Textarea(attrs={"rows": 3}),
            "task": forms.Textarea(attrs={"rows": 3}),
            "action": forms.Textarea(attrs={"rows": 5}),
            "result": forms.Textarea(attrs={"rows": 3}),
            "brainstorm": forms.Textarea(attrs={
                "rows": 16,
                "placeholder": "Dump everything you remember: what broke, who was involved, "
                               "what you tried, numbers, how it ended…",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and "questions" not in self.initial:
            self.initial["questions"] = list(self.instance.questions.all())

    def attached_questions(self):
        """Questions to show at the top of the page, keeping unsaved picks on a failed submit."""
        if self.is_bound:
            ids = [v for v in self.data.getlist("questions") if str(v).isdigit()]
            return list(Question.objects.for_user(self.owner).filter(pk__in=ids).prefetch_related("sightings"))
        return list(self.initial.get("questions") or [])

    def save(self, commit=True):
        name = self.cleaned_data.get("new_project", "").strip()
        if name:
            self.instance.project, _ = Project.objects.get_or_create(owner=self.owner, name=name)
        story = super().save(commit=commit)
        if commit:
            story.questions.set(self.cleaned_data.get("questions") or [])
        return story


class QuestionForm(TagsFieldMixin):
    owned_choice_fields = ("stories",)

    class Meta:
        model = Question
        fields = ["text", "category", "stories", "notes"]
        widgets = {
            "text": forms.TextInput(attrs={"placeholder": "e.g. Tell me about a time you disagreed with a teammate."}),
            "stories": forms.CheckboxSelectMultiple,
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {"stories": "Stories you'd use for this"}


class QuestionCreateForm(QuestionForm):
    """New-question form that can also record where you saw the question."""

    source = forms.ChoiceField(
        label="Where did you see it?", choices=SOURCE_OPTIONAL_CHOICES, required=False,
        initial=QuestionSighting.INTERVIEW,
    )
    company = forms.CharField(label="Company", max_length=120, required=False,
                              widget=forms.TextInput(attrs={"list": "company-suggestions", "autocomplete": "off"}))
    seen_on = forms.DateField(label="Date", required=False, widget=DATE_INPUT)

    def save(self, commit=True):
        question = super().save(commit=commit)
        source = self.cleaned_data.get("source")
        if commit and source:
            QuestionSighting.objects.create(
                question=question, source=source,
                company=self.cleaned_data.get("company", "").strip(),
                seen_on=self.cleaned_data.get("seen_on"),
            )
        return question


class SightingForm(forms.ModelForm):
    class Meta:
        model = QuestionSighting
        fields = ["source", "company", "seen_on"]
        widgets = {
            "seen_on": DATE_INPUT,
            "company": forms.TextInput(attrs={"list": "company-suggestions", "autocomplete": "off", "placeholder": "Optional"}),
        }
        labels = {"source": "Where", "seen_on": "Date"}


class BulkImportForm(forms.Form):
    text = forms.CharField(
        label="Paste your questions",
        help_text="One per line. Bullets, numbering and “Q1:” prefixes are cleaned up automatically.",
        widget=forms.Textarea(attrs={
            "rows": 10,
            "placeholder": "1. Tell me about a time you had to learn something quickly.\n"
                           "2. Why do you want to work here?\n"
                           "- What's the difference between a process and a thread?",
        }),
    )
    category = forms.ChoiceField(
        label="Category",
        choices=[("", "Auto-detect for each question")] + Question.CATEGORY_CHOICES,
        required=False,
    )
    source = forms.ChoiceField(label="Where did you see these?", choices=SOURCE_OPTIONAL_CHOICES,
                               required=False, initial=QuestionSighting.INTERVIEW)
    company = forms.CharField(label="Company", max_length=120, required=False,
                              widget=forms.TextInput(attrs={"list": "company-suggestions", "autocomplete": "off"}))
    seen_on = forms.DateField(label="Date", required=False, widget=DATE_INPUT)
    tags_text = forms.CharField(
        label="Tags", required=False, help_text="Optional. Added to every imported question.",
        widget=forms.TextInput(attrs={"list": "tag-suggestions", "autocomplete": "off"}),
    )


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class AttemptForm(forms.ModelForm):
    class Meta:
        model = PracticeAttempt
        fields = ["rating", "duration_seconds", "answer_text", "notes", "ai_feedback"]
        widgets = {
            "rating": forms.RadioSelect,
            "duration_seconds": forms.HiddenInput,
            "answer_text": forms.HiddenInput,
            "ai_feedback": forms.HiddenInput,
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "What would you change next time?"}),
        }
        labels = {"rating": "How did that go?", "notes": "Notes to self"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Drop the "---------" blank option Django adds for fields without a default.
        self.fields["rating"].choices = PracticeAttempt.RATING_CHOICES
