from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.utils import confirm_delete

from . import ai, importing, srs
from .forms import (
    AttemptForm, BulkImportForm, QuestionCreateForm, QuestionForm,
    SightingForm, StoryForm, parse_tags,
)
from .models import PracticeAttempt, Project, Question, QuestionSighting, Story, Tag


# ---------------------------------------------------------------- helpers

def _all_tags(user):
    return Tag.objects.for_user(user).order_by("name")


def _all_companies(user):
    return (
        QuestionSighting.objects.for_user(user).exclude(company="")
        .values_list("company", flat=True).distinct().order_by("company")
    )


SEEN_CHOICES = [
    ("", "Seen anywhere or not"),
    ("any", "Seen in interviews or applications"),
    ("interview", "Asked in interviews"),
    ("application", "On applications"),
    ("unseen", "Not seen yet"),
]


def _filter_seen(qs, seen):
    if seen == "any":
        return qs.filter(sightings__isnull=False).distinct()
    if seen in (QuestionSighting.INTERVIEW, QuestionSighting.APPLICATION):
        return qs.filter(sightings__source=seen).distinct()
    if seen == "unseen":
        return qs.filter(sightings__isnull=True)
    return qs


_confirm_delete = confirm_delete


def practice_streak(user, today=None):
    """Consecutive days (ending today or yesterday) with at least one attempt."""
    today = today or timezone.localdate()
    days = {
        timezone.localtime(dt).date()
        for dt in PracticeAttempt.objects.for_user(user).values_list("created_at", flat=True)
    }
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


# ---------------------------------------------------------------- dashboard

def dashboard(request):
    user = request.user
    now = timezone.now()
    questions = Question.objects.for_user(user)
    behavioural_without_story = (
        questions.filter(category=Question.BEHAVIORAL)
        .annotate(n=Count("stories"))
        .filter(n=0)
    )
    stories = Story.objects.for_user(user)
    incomplete = [s for s in stories if not s.is_complete]
    attempts = PracticeAttempt.objects.for_user(user)
    context = {
        "story_count": stories.count(),
        "question_count": questions.count(),
        "due_count": questions.filter(due_at__lte=now).count(),
        "attempt_count": attempts.count(),
        "streak": practice_streak(user),
        "recent_attempts": attempts.select_related("question")[:5],
        "uncovered_questions": behavioural_without_story[:5],
        "uncovered_count": behavioural_without_story.count(),
        "incomplete_stories": incomplete[:5],
        "incomplete_count": len(incomplete),
        "tag_coverage": Tag.objects.for_user(user).annotate(n=Count("stories")).order_by("-n", "name"),
        "most_seen": (
            questions.annotate(n=Count("sightings")).filter(n__gt=0)
            .prefetch_related("sightings").order_by("-n", "text")[:5]
        ),
    }
    return render(request, "prep/dashboard.html", context)


# ---------------------------------------------------------------- stories

def story_list(request):
    stories = Story.objects.for_user(request.user).select_related("project").prefetch_related("tags")
    q = request.GET.get("q", "").strip()
    tag = request.GET.get("tag", "")
    project = request.GET.get("project", "")
    if q:
        stories = stories.filter(
            Q(title__icontains=q) | Q(situation__icontains=q) | Q(task__icontains=q)
            | Q(action__icontains=q) | Q(result__icontains=q) | Q(brainstorm__icontains=q)
        )
    if tag:
        stories = stories.filter(tags__name=tag)
    if project:
        stories = stories.filter(project_id=project)
    return render(request, "prep/story_list.html", {
        "stories": stories.distinct(),
        "tags": _all_tags(request.user),
        "projects": Project.objects.for_user(request.user),
        "q": q, "active_tag": tag, "active_project": project,
    })


def story_detail(request, pk):
    story = get_object_or_404(Story.objects.for_user(request.user).select_related("project"), pk=pk)
    return render(request, "prep/story_detail.html", {"story": story})


def story_form(request, pk=None):
    user = request.user
    story = get_object_or_404(Story.objects.for_user(user), pk=pk) if pk else None
    initial = {}
    from_question = None
    qid = request.GET.get("question", "")
    if not story and qid.isdigit():
        from_question = Question.objects.for_user(user).filter(pk=qid).first()
        if from_question:
            initial["questions"] = [from_question]

    form = StoryForm(request.POST or None, instance=story, initial=initial, owner=user)
    if request.method == "POST" and form.is_valid():
        story = form.save()
        messages.success(request, "Story saved.")
        return redirect(story)

    attached = form.attached_questions()
    available = (
        Question.objects.for_user(user).exclude(pk__in=[q.pk for q in attached])
        .order_by("category", "text")
    )
    if story:
        back_url = story.get_absolute_url()
    elif from_question:
        back_url = from_question.get_absolute_url()
    else:
        back_url = reverse("prep:story_list")
    return render(request, "prep/story_form.html", {
        "form": form, "story": story, "tags": _all_tags(user),
        "attached": attached, "available": available, "back_url": back_url,
    })


def story_delete(request, pk):
    story = get_object_or_404(Story.objects.for_user(request.user), pk=pk)
    return _confirm_delete(request, story, "story", reverse("prep:story_list"))


# ---------------------------------------------------------------- questions

QUESTION_SORTS = [("", "A–Z"), ("seen", "Most seen"), ("recent", "Recently added"), ("due", "Due soonest")]


def question_list(request):
    user = request.user
    questions = Question.objects.for_user(user).prefetch_related("tags", "sightings").annotate(
        story_count=Count("stories", distinct=True),
        sighting_count=Count("sightings", distinct=True),
    )
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    tag = request.GET.get("tag", "")
    seen = request.GET.get("seen", "")
    sort = request.GET.get("sort", "")
    project = request.GET.get("project", "")
    if q:
        questions = questions.filter(
            Q(text__icontains=q) | Q(notes__icontains=q) | Q(sightings__company__icontains=q)
        )
    if category:
        questions = questions.filter(category=category)
    if tag:
        questions = questions.filter(tags__name=tag)
    questions = _filter_seen(questions, seen)
    if project.isdigit():
        questions = questions.filter(project_id=int(project))
    order = {"seen": ["-sighting_count", "text"], "recent": ["-created_at"], "due": ["due_at"]}.get(sort, ["text"])
    return render(request, "prep/question_list.html", {
        "questions": questions.distinct().order_by(*order),
        "tags": _all_tags(user),
        "categories": Question.CATEGORY_CHOICES,
        "seen_choices": SEEN_CHOICES,
        "projects": Project.objects.for_user(user).filter(practice_questions__isnull=False).distinct(),
        "active_project": project,
        "sorts": QUESTION_SORTS,
        "q": q, "active_category": category, "active_tag": tag, "active_seen": seen, "active_sort": sort,
        "filtering": bool(q or category or tag or seen or project),
    })


def question_detail(request, pk):
    question = get_object_or_404(Question.objects.for_user(request.user), pk=pk)
    return render(request, "prep/question_detail.html", {
        "question": question,
        "stories": question.stories.prefetch_related("tags"),
        "attempts": question.attempts.all()[:20],
        "sightings": question.sightings.all(),
        "sighting_form": SightingForm(),
        "companies": _all_companies(request.user),
    })


@require_POST
def question_add_sighting(request, pk):
    question = get_object_or_404(Question.objects.for_user(request.user), pk=pk)
    form = SightingForm(request.POST)
    if form.is_valid():
        sighting = form.save(commit=False)
        sighting.question = question
        sighting.save()
        messages.success(request, "Logged. That's one more time you've seen this question.")
    else:
        messages.error(request, "Couldn't log that. Check the date.")
    return redirect(question)


@require_POST
def sighting_delete(request, pk):
    sighting = get_object_or_404(QuestionSighting.objects.for_user(request.user), pk=pk)
    question = sighting.question
    sighting.delete()
    messages.success(request, "Removed that entry.")
    return redirect(question)


def question_form(request, pk=None):
    user = request.user
    question = get_object_or_404(Question.objects.for_user(user), pk=pk) if pk else None
    form_class = QuestionForm if question else QuestionCreateForm
    form = form_class(request.POST or None, instance=question, owner=user)
    if request.method == "POST" and form.is_valid():
        question = form.save()
        messages.success(request, "Question saved.")
        return redirect(question)
    return render(request, "prep/question_form.html", {
        "form": form, "question": question, "tags": _all_tags(user), "companies": _all_companies(user),
    })


def question_import(request):
    """Paste a list of questions -> preview and tidy -> import."""
    form = BulkImportForm(request.POST or None)
    rows = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if request.POST.get("action") == "import":
            include = set(request.POST.getlist("row_include"))
            texts = request.POST.getlist("row_text")
            cats = request.POST.getlist("row_category")
            chosen = [(t, c) for i, (t, c) in enumerate(zip(texts, cats)) if str(i) in include]
            created, repeats = importing.import_rows(
                request.user, chosen, source=data["source"], company=data["company"],
                seen_on=data["seen_on"], tag_names=parse_tags(data["tags_text"]),
            )
            if not created and not repeats:
                messages.error(request, "Nothing was selected to import.")
            else:
                parts = []
                if created:
                    parts.append(f"added {len(created)} new question{'s' if len(created) != 1 else ''}")
                if repeats:
                    verb = "logged another sighting for" if data["source"] else "skipped"
                    parts.append(f"{verb} {len(repeats)} you already had")
                messages.success(request, "Done: " + " and ".join(parts) + ".")
                return redirect(f"{reverse('prep:question_list')}?sort=recent")
            texts = [t for t in texts if t.strip()]
        else:
            texts = importing.parse_questions(data["text"])
        rows = importing.build_preview(request.user, texts, data["category"])
        if not rows:
            form.add_error("text", "Couldn't find any questions in that text.")
            rows = None
    return render(request, "prep/question_import.html", {
        "form": form,
        "rows": rows,
        "new_count": sum(1 for r in rows if not r["existing"]) if rows else 0,
        "categories": Question.CATEGORY_CHOICES,
        "tags": _all_tags(request.user),
        "companies": _all_companies(request.user),
    })


def question_delete(request, pk):
    question = get_object_or_404(Question.objects.for_user(request.user), pk=pk)
    return _confirm_delete(request, question, "question", reverse("prep:question_list"))


# ---------------------------------------------------------------- projects

def project_list(request):
    return redirect("journal:project_list", permanent=True)


def project_detail(request, pk):
    return redirect("journal:project_detail", pk=pk, permanent=True)


# ---------------------------------------------------------------- practice

PRACTICE_MODES = [("due", "Due for review"), ("random", "Random")]


def _practice_filters(data):
    mode = data.get("mode", "due")
    return {
        "mode": mode if mode in dict(PRACTICE_MODES) else "due",
        "category": data.get("category", ""),
        "tag": data.get("tag", ""),
        "seen": data.get("seen", "") if data.get("seen", "") in dict(SEEN_CHOICES) else "",
        "project": data.get("project", "") if str(data.get("project", "")).isdigit() else "",
    }


def pick_question(user, mode="due", category="", tag="", seen="", project="", exclude_id=None):
    qs = _filter_seen(Question.objects.for_user(user), seen)
    if project:
        qs = qs.filter(project_id=project)
    if category:
        qs = qs.filter(category=category)
    if tag:
        qs = qs.filter(tags__name=tag)
    if mode == "random":
        pool = qs.exclude(pk=exclude_id) if exclude_id else qs
        return pool.order_by("?").first() or qs.first()
    return qs.filter(due_at__lte=timezone.now()).order_by("due_at").first()


def practice(request):
    user = request.user
    questions = Question.objects.for_user(user)
    filters = _practice_filters(request.GET)
    question_id = request.GET.get("question")
    if question_id:
        question = get_object_or_404(questions, pk=question_id)
    else:
        last = request.GET.get("last", "")
        question = pick_question(user, **filters, exclude_id=last if last.isdigit() else None)

    next_due = None
    if question is None:
        next_due = questions.order_by("due_at").values_list("due_at", flat=True).first()

    return render(request, "prep/practice.html", {
        "question": question,
        "stories": question.stories.prefetch_related("tags") if question else [],
        "form": AttemptForm(),
        "filters": filters,
        "skip_query": urlencode({**filters, "mode": "random", "last": question.pk if question else ""}),
        "random_query": urlencode({**filters, "mode": "random"}),
        "seen_choices": SEEN_CHOICES,
        "sightings": question.sightings.all() if question else [],
        "source_note": question.source_note if question else None,
        "practice_projects": Project.objects.for_user(user).filter(practice_questions__isnull=False).distinct(),
        "modes": PRACTICE_MODES,
        "categories": Question.CATEGORY_CHOICES,
        "tags": _all_tags(user),
        "due_count": questions.filter(due_at__lte=timezone.now()).count(),
        "has_questions": questions.exists(),
        "next_due": next_due,
        "ai_enabled": ai.is_enabled(user),
    })


@require_POST
def practice_rate(request, pk):
    question = get_object_or_404(Question.objects.for_user(request.user), pk=pk)
    form = AttemptForm(request.POST)
    filters = _practice_filters(request.POST)
    if form.is_valid():
        attempt = form.save(commit=False)
        attempt.question = question
        attempt.save()
        srs.schedule(question, attempt.rating)
        question.save(update_fields=["ease", "interval_days", "repetitions", "due_at"])
        when = timezone.localtime(question.due_at)
        if question.interval_days == 0:
            messages.info(request, "Saved. This one will come back in a few minutes.")
        else:
            days = question.interval_days
            messages.success(request, f"Saved. Next review in {days} day{'s' if days != 1 else ''} ({when:%a %b %d}).")
    else:
        messages.error(request, "Pick a rating before saving.")
        return redirect(f"{reverse('prep:practice')}?{urlencode({**filters, 'question': pk})}")
    return redirect(f"{reverse('prep:practice')}?{urlencode({**filters, 'last': pk})}")


@require_POST
def practice_feedback(request, pk):
    question = get_object_or_404(Question.objects.for_user(request.user), pk=pk)
    if not ai.is_enabled(request.user):
        return JsonResponse({"error": "AI feedback isn't available here."}, status=400)
    try:
        feedback = ai.get_feedback(question.text, request.POST.get("answer", ""))
    except ai.AIFeedbackError as e:
        return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"feedback": feedback})


def history(request):
    attempts = PracticeAttempt.objects.for_user(request.user).select_related("question")
    rating = request.GET.get("rating", "")
    if rating.isdigit():
        attempts = attempts.filter(rating=int(rating))
    return render(request, "prep/history.html", {
        "attempts": attempts[:200],
        "ratings": PracticeAttempt.RATING_CHOICES,
        "active_rating": rating,
    })
