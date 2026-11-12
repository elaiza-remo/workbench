from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.utils import confirm_delete
from prep.models import Project, Story, Tag

from .forms import NoteForm, ProjectForm
from .gitsync import GitError, can_sync, sync_project
from .models import Commit, Note
from .practice import create_questions, suggest_questions

AI_TOOL_SUGGESTIONS = ["Claude", "ChatGPT", "GitHub Copilot", "Cursor", "Gemini"]


def _kind_counts(notes_qs):
    counts = dict(notes_qs.order_by().values_list("kind").annotate(n=Count("id")))
    return [(value, label, counts.get(value, 0)) for value, label in Note.KIND_CHOICES]


# ---------------------------------------------------------------- projects

def project_list(request):
    status = request.GET.get("status", "")
    user = request.user
    projects = Project.objects.for_user(user).annotate(
        note_count=Count("notes", distinct=True),
        commit_count=Count("commits", distinct=True),
        story_count=Count("stories", distinct=True),
        last_commit=Max("commits__committed_at"),
    )
    if status:
        projects = projects.filter(status=status)
    return render(request, "journal/project_list.html", {
        "projects": projects,
        "statuses": Project.STATUS_CHOICES,
        "active_status": status,
        "recent_notes": Note.objects.for_user(user).select_related("project")[:6],
    })


def project_detail(request, pk):
    project = get_object_or_404(Project.objects.for_user(request.user), pk=pk)
    tab = request.GET.get("tab", "notes")
    context = {
        "project": project,
        "tab": tab,
        "kind_counts": _kind_counts(project.notes.all()),
        "note_count": project.notes.count(),
        "commit_count": project.commits.count(),
        "story_count": project.stories.count(),
        "practice_count": project.practice_questions.count(),
        "kinds": Note.KIND_CHOICES,
        "can_sync": can_sync(project, request.user),
    }
    if tab == "commits":
        commits = project.commits.annotate(note_count=Count("notes")).order_by("-committed_at", "-id")
        if request.GET.get("filter") == "noted":
            commits = commits.filter(note_count__gt=0)
        q = request.GET.get("q", "").strip()
        if q:
            commits = commits.filter(Q(message__icontains=q) | Q(sha__startswith=q))
        context.update({
            "page": Paginator(commits, 50).get_page(request.GET.get("page")),
            "q": q, "commit_filter": request.GET.get("filter", ""),
        })
    elif tab == "stories":
        context["stories"] = project.stories.prefetch_related("tags")
    else:
        kind = request.GET.get("kind", "")
        notes = project.notes.prefetch_related("tags", "commits")
        if kind:
            notes = notes.filter(kind=kind)
        context.update({"notes": notes, "active_kind": kind})
    return render(request, "journal/project_detail.html", context)


def project_form(request, pk=None):
    project = get_object_or_404(Project.objects.for_user(request.user), pk=pk) if pk else None
    form = ProjectForm(request.POST or None, instance=project, owner=request.user)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, "Project saved.")
        return redirect(project)
    return render(request, "journal/project_form.html", {"form": form, "project": project})


def project_delete(request, pk):
    return confirm_delete(
        request, get_object_or_404(Project.objects.for_user(request.user), pk=pk), "project",
        reverse("journal:project_list"),
        warning="Its journal notes and imported commits will be deleted. Your stories and practice questions are kept, just without a project.",
    )


@require_POST
def project_sync(request, pk):
    project = get_object_or_404(Project.objects.for_user(request.user), pk=pk)
    if not can_sync(project, request.user):
        messages.error(request, "Commit import isn't available for this project.")
        return redirect(f"{project.get_absolute_url()}?tab=commits")
    try:
        new, total = sync_project(project)
    except GitError as e:
        messages.error(request, f"Couldn't import commits: {e}")
    else:
        if new:
            messages.success(request, f"Imported {new} new commit{'s' if new != 1 else ''}.")
        else:
            messages.info(request, f"Already up to date ({total} commits).")
    return redirect(f"{project.get_absolute_url()}?tab=commits")


# ---------------------------------------------------------------- commits

def commit_detail(request, pk):
    commit = get_object_or_404(Commit.objects.for_user(request.user).select_related("project"), pk=pk)
    return render(request, "journal/commit_detail.html", {
        "commit": commit,
        "notes": commit.notes.all(),
        "kinds": Note.KIND_CHOICES,
    })


# ---------------------------------------------------------------- notes

def _filtered_notes(user, params):
    notes = Note.objects.for_user(user).select_related("project").prefetch_related("tags", "commits")
    filters = {k: params.get(k, "").strip() for k in ("q", "kind", "project", "tag", "tool")}
    if filters["q"]:
        q = filters["q"]
        notes = notes.filter(
            Q(title__icontains=q) | Q(context__icontains=q) | Q(details__icontains=q)
            | Q(outcome__icontains=q) | Q(commits__message__icontains=q)
        )
    if filters["kind"]:
        notes = notes.filter(kind=filters["kind"])
    if filters["project"].isdigit():
        notes = notes.filter(project_id=int(filters["project"]))
    if filters["tag"]:
        notes = notes.filter(tags__name=filters["tag"])
    if filters["tool"]:
        notes = notes.filter(ai_tool__iexact=filters["tool"])
    return notes.distinct(), filters


def note_list(request):
    user = request.user
    notes, filters = _filtered_notes(user, request.GET)
    query = urlencode({k: v for k, v in filters.items() if v})
    return render(request, "journal/note_list.html", {
        "notes": notes,
        "filters": filters,
        "filtering": any(filters.values()),
        "export_query": query,
        "kinds": Note.KIND_CHOICES,
        "kind_counts": _kind_counts(Note.objects.for_user(user)),
        "projects": Project.objects.for_user(user),
        "tags": Tag.objects.for_user(user).filter(project_notes__isnull=False).distinct(),
        "tools": Note.objects.for_user(user).exclude(ai_tool="").values_list("ai_tool", flat=True).distinct().order_by("ai_tool"),
    })


def note_export(request):
    """Download the filtered notes as one Markdown file."""
    notes, filters = _filtered_notes(request.user, request.GET)
    notes = notes.order_by("project__name", "-happened_on")
    kind_label = dict(Note.KIND_CHOICES).get(filters["kind"], "")
    project = Project.objects.for_user(request.user).filter(pk=filters["project"]).first() if filters["project"].isdigit() else None
    title = " · ".join(x for x in [project.name if project else "", kind_label or "Project notes"] if x)

    lines = [f"# {title}", "", f"*Exported {timezone.localdate():%B} {timezone.localdate().day}, {timezone.localdate().year}*", ""]
    current = None
    for note in notes:
        if not project and note.project_id != current:
            current = note.project_id
            lines += [f"## {note.project.name}", ""]
        lines.append(note.as_markdown(heading_level=3 if not project else 2))
        lines.append("---\n")
    if not notes:
        lines.append("_No notes match these filters._")

    filename = slugify(title) or "notes"
    response = HttpResponse("\n".join(lines), content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.md"'
    return response


def note_detail(request, pk):
    note = get_object_or_404(Note.objects.for_user(request.user).select_related("project"), pk=pk)
    return render(request, "journal/note_detail.html", {
        "note": note,
        "commits": note.commits.all(),
        "stories": note.stories.all(),
        "markdown": note.as_markdown(heading_level=2, include_project=True),
    })


def note_form(request, pk=None):
    user = request.user
    note = get_object_or_404(Note.objects.for_user(user), pk=pk) if pk else None
    initial = {}
    commit = None
    if not note:
        project_id = request.GET.get("project", "")
        commit_id = request.GET.get("commit", "")
        if commit_id.isdigit():
            commit = Commit.objects.for_user(user).filter(pk=commit_id).first()
            if commit:
                project_id = str(commit.project_id)
                initial["commits"] = [commit]
        if project_id.isdigit():
            initial["project"] = Project.objects.for_user(user).filter(pk=project_id).first()
        if request.GET.get("kind") in dict(Note.KIND_CHOICES):
            initial["kind"] = request.GET["kind"]

    form = NoteForm(request.POST or None, instance=note, initial=initial, owner=user)
    if request.method == "POST" and form.is_valid():
        note = form.save()
        messages.success(request, "Note saved.")
        return redirect(note)

    if note:
        back_url = note.get_absolute_url()
    elif commit:
        back_url = commit.get_absolute_url()
    elif initial.get("project"):
        back_url = initial["project"].get_absolute_url()
    else:
        back_url = reverse("journal:note_list")
    return render(request, "journal/note_form.html", {
        "form": form,
        "note": note,
        "back_url": back_url,
        "labels": Note.FIELD_LABELS,
        "ai_tools": AI_TOOL_SUGGESTIONS,
        "tags": Tag.objects.for_user(user),
    })


def note_delete(request, pk):
    note = get_object_or_404(Note.objects.for_user(request.user), pk=pk)
    return confirm_delete(request, note, "note", note.project.get_absolute_url())


# How each kind of note maps onto a STAR draft. Everything also goes into brainstorm.
STAR_DRAFT = {
    Note.DECISION: {"situation": "context", "action": "outcome"},
    Note.ISSUE: {"situation": "context", "action": "details", "result": "outcome"},
    Note.AI: {"situation": "context", "action": "outcome"},
    Note.LEARNING: {"situation": "details", "result": "context"},
    Note.NOTE: {"situation": "context"},
}


@require_POST
def note_to_story(request, pk):
    """Draft a STAR story from a note, then open it for editing."""
    note = get_object_or_404(Note.objects.for_user(request.user), pk=pk)
    story = Story(
        owner=request.user,
        title=note.title,
        project=note.project,
        brainstorm=f"From project note: {note.title}\n\n" + note.as_markdown(heading_level=2).split("\n", 1)[1].strip(),
    )
    for star_field, note_field in STAR_DRAFT.get(note.kind, {}).items():
        setattr(story, star_field, getattr(note, note_field))
    story.save()
    story.tags.set(note.tags.all())
    note.stories.add(story)
    messages.success(request, "Drafted a story from your note. Shape it into STAR, then save.")
    return redirect("prep:story_update", pk=story.pk)


# ---------------------------------------------------------------- practice questions

def project_questions(request, pk):
    """Suggest practice questions from a project's notes, then add the chosen ones."""
    project = get_object_or_404(Project.objects.for_user(request.user), pk=pk)
    note = None
    note_id = request.GET.get("note") or request.POST.get("note", "")
    if str(note_id).isdigit():
        note = get_object_or_404(project.notes, pk=note_id)

    if request.method == "POST":
        include = set(request.POST.getlist("row_include"))
        texts = request.POST.getlist("row_text")
        note_ids = request.POST.getlist("row_note")
        notes = {n.pk: n for n in project.notes.all()}
        rows = []
        for i, (text, nid) in enumerate(zip(texts, note_ids)):
            if str(i) in include and text.strip():
                rows.append((text, notes.get(int(nid)) if nid.isdigit() else None))
        created = create_questions(project, rows)
        if created:
            messages.success(
                request,
                f"Added {len(created)} practice question{'s' if len(created) != 1 else ''} for {project.name}. "
                "They're due now.",
            )
            return redirect(f"{reverse('prep:practice')}?{urlencode({'project': project.pk})}")
        messages.error(request, "Nothing new was added. Tick at least one question that isn't already in your library.")

    suggestions = suggest_questions(project, note)
    return render(request, "journal/project_questions.html", {
        "project": project,
        "note": note,
        "suggestions": suggestions,
        "new_count": sum(1 for s in suggestions if not s["existing"]),
        "question_count": project.practice_questions.count(),
        "note_count": project.notes.exclude(kind=Note.NOTE).count(),
    })
