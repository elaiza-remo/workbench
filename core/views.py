import hmac
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.db.models import Count, Max
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from journal.models import Note
from prep.models import Project, Question, Story
from prep.views import practice_streak

from . import activity
from .demo import get_demo_user, reset_demo


@login_not_required
def home(request):
    """Signed out: the public landing page. Signed in: your dashboard."""
    if not request.user.is_authenticated:
        return landing(request)
    user = request.user
    now = timezone.now()
    week_ago = timezone.localdate() - timedelta(days=7)
    notes = Note.objects.for_user(user)
    questions = Question.objects.for_user(user)
    active = (
        Project.objects.for_user(user).filter(status=Project.ACTIVE)
        .annotate(note_count=Count("notes", distinct=True), last_commit=Max("commits__committed_at"))
        .order_by("name")[:6]
    )
    return render(request, "core/home.html", {
        "due_count": questions.filter(due_at__lte=now).count(),
        "story_count": Story.objects.for_user(user).count(),
        "question_count": questions.count(),
        "streak": practice_streak(user),
        "project_count": Project.objects.for_user(user).count(),
        "note_count": notes.count(),
        "notes_this_week": notes.filter(happened_on__gte=week_ago).count(),
        "active_projects": active,
        "recent_notes": notes.select_related("project")[:5],
        "graph": activity.build(user),
    })


def landing(request):
    """Public overview of the app: why it exists, what it does, and a way into the demo."""
    demo = get_user_model().objects.filter(username=settings.DEMO_USERNAME).first()
    preview = activity.build(demo) if demo and settings.DEMO_ENABLED else None
    return render(request, "core/landing.html", {
        "demo_enabled": settings.DEMO_ENABLED,
        "preview_graph": preview if preview and preview["total"] else None,
        "owner_name": settings.OWNER_NAME,
        "owner_url": settings.OWNER_URL,
        "repo_url": settings.REPO_URL,
    })


# ---------------------------------------------------------------- accounts

class LoginView(auth_views.LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "demo_enabled": settings.DEMO_ENABLED}


login_view = login_not_required(LoginView.as_view())


@login_not_required
@require_POST
def demo_login(request):
    """'Try the demo': sign in as the shared sandbox account."""
    if not settings.DEMO_ENABLED:
        return redirect("login")
    user = get_demo_user()
    if not Project.objects.for_user(user).exists():
        reset_demo()  # first visit ever, or someone deleted everything
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("home")


@login_not_required
@require_GET
def cron_reset_demo(request):
    """Called nightly by Vercel Cron with 'Authorization: Bearer <CRON_SECRET>'."""
    expected = f"Bearer {settings.CRON_SECRET}"
    given = request.headers.get("Authorization", "")
    if not settings.CRON_SECRET or not hmac.compare_digest(given, expected):
        return HttpResponseForbidden("Forbidden")
    reset_demo()
    return JsonResponse({"ok": True, "reset_at": timezone.now().isoformat()})
