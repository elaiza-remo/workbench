"""The public sandbox: a "demo" account full of realistic sample data.

Anyone can click "Try the demo" on the login page and use the whole app as this
account. Everything is fictional, and `reset_demo()` wipes and re-seeds it
(nightly via Vercel Cron, or `python manage.py reset_demo`).
"""
import hashlib
import random
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from journal.models import Commit, Note
from prep import srs
from prep.management.commands.seed_questions import seed_for
from prep.models import PracticeAttempt, Project, Question, QuestionSighting, Story, Tag

DEMO_PROJECTS = [
    {
        "name": "Pantry Pal",
        "status": Project.ACTIVE,
        "tech_stack": "Django, HTMX, PostgreSQL",
        "description": "Tracks what's in your kitchen and suggests meals before food goes bad.",
        "repo_url": "https://github.com/example/pantry-pal",
        "months_ago": 5,
        "commits": [
            "Initial Django project", "Add Pantry item model and admin", "Barcode lookup via Open Food Facts",
            "Expiry reminders as a daily digest", "Switch list pages to HTMX partials", "Fix timezone bug in expiry dates",
            "Add recipe suggestions from expiring items", "Cache recipe API responses for 24h",
            "Write tests for expiry calculations", "Mobile layout for the pantry list", "Add shopping list export",
        ],
    },
    {
        "name": "Trailhead",
        "status": Project.ACTIVE,
        "tech_stack": "Next.js, TypeScript, Mapbox",
        "description": "Finds beginner-friendly hikes near you with live trail conditions.",
        "repo_url": "https://github.com/example/trailhead",
        "months_ago": 3,
        "commits": [
            "Scaffold Next.js app", "Map view with Mapbox GL", "Load trails from the parks open-data API",
            "Filter by difficulty and distance", "Debounce map move events", "Add trail condition reports",
            "Fix hydration warning on trail cards", "Lighthouse pass: lazy-load map tiles",
        ],
    },
    {
        "name": "Study Buddy Bot",
        "status": Project.FINISHED,
        "tech_stack": "Python, discord.py, SQLite",
        "description": "Team capstone: a Discord bot that runs study sessions and quizzes for a course server.",
        "repo_url": "",
        "months_ago": 11,
        "commits": [
            "Bot skeleton and slash commands", "Pomodoro session command", "Quiz question bank",
            "Leaderboard with weekly reset", "Fix race condition in session timers", "Deploy notes and README",
        ],
    },
]

DEMO_NOTES = [
    ("Pantry Pal", Note.DECISION, "Used HTMX instead of a React frontend", 120,
     "I needed interactive lists (add, edit, filter) but I'm the only developer and wanted to ship in weeks, not months.",
     "React + Django REST API; plain Django forms with full page reloads; HTMX partials.",
     "HTMX kept everything in one Django codebase with server-rendered templates. Trade-off: less suited to offline use, which this app doesn't need."),
    ("Pantry Pal", Note.ISSUE, "Expiry dates were off by one day", 95,
     "Items added in the evening showed as expiring a day early for users in Mountain time.",
     "Checked the barcode data first, then logged raw datetimes and saw they were stored as UTC midnight.",
     "Stored expiry as a DateField instead of a DateTimeField and compared against the user's local date. Added tests for late-evening entries."),
    ("Pantry Pal", Note.AI, "Generated test cases for expiry logic", 80,
     "I wanted edge cases for the expiry calculation that I might not think of myself.",
     "A list of 12 test cases including leap years, DST changes and items with no expiry.",
     "Kept 9, rewrote 2 that asserted the wrong behaviour, and dropped one that duplicated another. All passing now."),
    ("Pantry Pal", Note.LEARNING, "Cache third-party API responses early", 60,
     "Free APIs rate-limit fast, and one slow upstream call can make your whole page feel broken.",
     "The recipe API started returning 429s during my own testing.",
     "Wrap external calls in a small cache from day one, with a sensible TTL."),
    ("Trailhead", Note.DECISION, "Chose Mapbox over Google Maps", 70,
     "I needed custom trail overlays and a free tier that wouldn't surprise me with a bill.",
     "Google Maps JS API; Leaflet + OpenStreetMap; Mapbox GL.",
     "Mapbox had the best vector styling for trail lines and a generous free tier. Leaflet was a close second and I'd pick it for a simpler map."),
    ("Trailhead", Note.ISSUE, "Map re-rendered on every pan", 5,
     "Panning the map made the trail list flicker and CPU spike.",
     "Profiled with React DevTools; the map's move event updated state on every frame.",
     "Debounced the move handler to 250ms and memoized the trail list. Render count dropped from ~60/s to 4/s."),
    ("Trailhead", Note.AI, "Used Claude to explain a hydration warning", 2,
     "Next.js showed a hydration mismatch on trail cards and the error message wasn't clear to me.",
     "An explanation that dates rendered differently on server and client because of time zones.",
     "Confirmed it by logging both values, then formatted dates on the client only. Understood the cause instead of just suppressing the warning."),
    ("Study Buddy Bot", Note.ISSUE, "Two sessions could start at once", 300,
     "Two teammates ran /study at the same moment and the bot started overlapping timers.",
     "Added logging and reproduced it with two test accounts.",
     "Added a per-channel asyncio lock around session start. Wrote a test that fires both commands concurrently."),
    ("Study Buddy Bot", Note.DECISION, "Kept SQLite instead of moving to Postgres", 320,
     "The team debated switching databases mid-project.",
     "Stay on SQLite; migrate to Postgres on a managed host.",
     "With one bot process and a few hundred rows, SQLite was simpler to run and back up. We documented when we'd revisit it."),
]

DEMO_STORIES = [
    {
        "title": "Fixing a timezone bug users kept reporting",
        "project": "Pantry Pal",
        "tags": ["debugging", "problem solving", "customer focus"],
        "situation": "Users in Mountain time reported items expiring a day early in Pantry Pal.",
        "task": "As the only developer, I had to find the cause and fix it without breaking existing data.",
        "action": "I reproduced it with a test account, logged raw values and found expiry dates were stored as UTC datetimes. I migrated the field to a plain date, compared against each user's local date, and added tests for evening entries.",
        "result": "The reports stopped, and the new tests caught a similar bug in the reminders feature a month later.",
        "questions": ["Tell me about a time you debugged something hard to track down.",
                      "Tell me about a time you dealt with a problem and solved it."],
    },
    {
        "title": "Resolving a race condition in our capstone bot",
        "project": "Study Buddy Bot",
        "tags": ["teamwork", "technical challenge"],
        "situation": "During our capstone demo week, the Discord bot started overlapping study timers.",
        "task": "I owned the session feature, so I volunteered to fix it before our demo.",
        "action": "I reproduced it with two accounts, added logging, and found two commands could start sessions at once. I added a per-channel lock and a test that fires both commands together, then walked the team through the fix.",
        "result": "The demo went smoothly, and our instructor called out the test as a good practice.",
        "questions": ["Tell me about the most technically challenging problem you've faced.",
                      "Tell me about a time you worked under a tight deadline."],
    },
    {
        "title": "Disagreeing about switching databases",
        "project": "Study Buddy Bot",
        "tags": ["conflict", "teamwork", "communication"],
        "situation": "Halfway through the project, a teammate wanted to move from SQLite to Postgres.",
        "task": "",
        "action": "I listed what each option would cost us in setup and risk, and suggested we agree on what would make us switch.",
        "result": "",
        "questions": ["Tell me about a time you disagreed with a teammate. How did you handle it?"],
    },
]

SIGHTINGS = [
    ("Tell me about yourself.", "interview", "Northwind Labs", 20),
    ("Tell me about yourself.", "interview", "Bluefin Health", 9),
    ("Tell me about a time you disagreed with a teammate. How did you handle it?", "interview", "Northwind Labs", 20),
    ("Why do you want to work here?", "application", "Bluefin Health", 15),
    ("Explain the difference between a process and a thread.", "interview", "Cobalt Software", 4),
    ("Tell me about a time you debugged something hard to track down.", "interview", "Cobalt Software", 4),
]


def _sha(seed):
    return hashlib.sha1(seed.encode()).hexdigest()


def get_demo_user():
    User = get_user_model()
    user, created = User.objects.get_or_create(username=settings.DEMO_USERNAME, defaults={"first_name": "Demo"})
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


@transaction.atomic
def reset_demo():
    """Delete everything the demo account owns and seed fresh sample data."""
    user = get_demo_user()
    for model in (Question, Story, Project, Tag):  # notes, commits, attempts, sightings cascade
        model.objects.filter(owner=user).delete()
    seed_demo(user)
    return user


def seed_demo(user, today=None):
    rng = random.Random(7)
    today = today or timezone.localdate()
    tz = timezone.get_current_timezone()

    def at(days_ago, hour=None):
        hour = rng.randint(9, 22) if hour is None else hour
        return timezone.make_aware(datetime.combine(today - timedelta(days=days_ago), time(hour, rng.randint(0, 59))), tz)

    seed_for(user)
    questions = {q.text: q for q in Question.objects.filter(owner=user)}

    tags = {}

    def tag(name):
        if name not in tags:
            tags[name] = Tag.objects.get_or_create(owner=user, name=name)[0]
        return tags[name]

    # Projects and their commit history, spread over each project's lifetime.
    projects = {}
    for spec in DEMO_PROJECTS:
        project = Project.objects.create(
            owner=user, name=spec["name"], status=spec["status"], tech_stack=spec["tech_stack"],
            description=spec["description"], repo_url=spec["repo_url"],
            started_on=today - timedelta(days=spec["months_ago"] * 30),
        )
        projects[spec["name"]] = project
        span = spec["months_ago"] * 30
        end = 200 if spec["status"] == Project.FINISHED else 0
        commits = []
        messages = list(spec["commits"])
        # Plenty of small commits between the named milestones, like real history.
        filler = ["Refactor views", "Fix typo in template", "Tidy up CSS", "Update README", "Add tests",
                  "Rename variables for clarity", "Handle empty states", "Bump dependencies", "Small UI fixes"]
        n = len(messages) * 4
        for i in range(n):
            days_ago = end + int((span - end) * (1 - i / max(n - 1, 1)) ** 1.15)
            msg = messages[i // 4] if i % 4 == 0 else rng.choice(filler)
            added = rng.randint(3, 180)
            commits.append(Commit(
                project=project, sha=_sha(f"{spec['name']}-{i}"), message=msg, author="Demo User",
                committed_at=at(days_ago), files_changed=rng.randint(1, 9),
                insertions=added, deletions=rng.randint(0, added // 2),
            ))
        Commit.objects.bulk_create(commits)

    # Journal notes, linked to a nearby commit.
    notes = {}
    for project_name, kind, title, days_ago, context, details, outcome in DEMO_NOTES:
        project = projects[project_name]
        note = Note.objects.create(
            project=project, kind=kind, title=title, context=context, details=details, outcome=outcome,
            ai_tool="Claude" if kind == Note.AI else "", happened_on=today - timedelta(days=days_ago),
        )
        Note.objects.filter(pk=note.pk).update(created_at=at(days_ago))
        nearby = project.commits.filter(committed_at__date__lte=today - timedelta(days=days_ago)).first()
        if nearby:
            note.commits.add(nearby)
        notes[title] = note

    # STAR stories (one deliberately unfinished, so the "gaps" panel has something to show).
    for spec in DEMO_STORIES:
        story = Story.objects.create(
            owner=user, title=spec["title"], project=projects[spec["project"]],
            situation=spec["situation"], task=spec["task"], action=spec["action"], result=spec["result"],
            brainstorm="Rough notes:\n- " + "\n- ".join(s for s in (spec["situation"], spec["action"]) if s),
        )
        story.tags.set([tag(t) for t in spec["tags"]])
        for text in spec["questions"]:
            if text in questions:
                questions[text].stories.add(story)
    notes["Expiry dates were off by one day"].stories.add(Story.objects.get(owner=user, title__startswith="Fixing a timezone"))

    # Practice questions generated from a project's notes.
    from journal.practice import create_questions, suggest_questions

    pantry = projects["Pantry Pal"]
    rows = [(s["text"], s["note"]) for s in suggest_questions(pantry) if not s["existing"]][:5]
    create_questions(pantry, rows)

    # Where questions came up.
    for text, source, company, days_ago in SIGHTINGS:
        if text in questions:
            QuestionSighting.objects.create(
                question=questions[text], source=source, company=company, seen_on=today - timedelta(days=days_ago),
            )

    # A few months of practice, so history, streaks and the activity graph look lived-in.
    pool = list(Question.objects.filter(owner=user))
    for days_ago in range(120, -1, -1):
        busy = days_ago < 6 or rng.random() < (0.45 if days_ago < 45 else 0.2)
        if not busy:
            continue
        for _ in range(rng.randint(1, 4)):
            q = rng.choice(pool)
            rating = rng.choices([1, 2, 3, 4], weights=[1, 2, 4, 2])[0]
            attempt = PracticeAttempt.objects.create(
                question=q, rating=rating, duration_seconds=rng.randint(45, 180),
                notes=rng.choice(["", "", "Lead with the result next time.", "Too long on the situation.", "Good pacing."]),
            )
            PracticeAttempt.objects.filter(pk=attempt.pk).update(created_at=at(days_ago))
            srs.schedule(q, rating, now=at(days_ago))
            q.save(update_fields=["ease", "interval_days", "repetitions", "due_at"])
    # Make sure a handful are due so practice mode has something to show.
    Question.objects.filter(owner=user, pk__in=[q.pk for q in pool[:6]]).update(due_at=timezone.now())
