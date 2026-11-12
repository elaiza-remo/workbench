# Workbench developer guide

How to run Workbench, find your way around the code, and make changes safely.
For what the app *does*, see [README.md](README.md). To put it online, see [DEPLOY.md](DEPLOY.md).

**Contents**

1. [Getting started](#1-getting-started)
2. [How the project is organized](#2-how-the-project-is-organized)
3. [How a page works: URL → view → template](#3-how-a-page-works-url--view--template)
4. [The data model](#4-the-data-model)
5. [Recipes for common changes](#5-recipes-for-common-changes)
6. [The database](#6-the-database)
7. [Tests](#7-tests)
8. [Front end: styles, theme and tabs](#8-front-end-styles-theme-and-tabs)
9. [Management commands](#9-management-commands)
10. [Using git with this project](#10-using-git-with-this-project)
11. [Troubleshooting](#11-troubleshooting)
12. [Going further](#12-going-further)

---

## 1. Getting started

### First time on a new machine

Requires Python 3.10 or newer. On macOS the command is `python3` until the virtual environment is active.

```bash
cd interview-prep
python3 -m venv .venv              # create an isolated Python environment (once)
source .venv/bin/activate          # turn it on (Windows: .venv\Scripts\activate)
pip install -r requirements.txt    # install Django
python manage.py migrate           # create/update the database tables
python manage.py createsuperuser   # your login (every page needs one)
python manage.py seed_questions    # optional: 30 starter interview questions
python manage.py runserver         # start the site
```

Open http://127.0.0.1:8000 and sign in. **Try the demo** on the login page signs you in as the sample-data account instead.

### Every day after that

```bash
cd interview-prep
source .venv/bin/activate          # your prompt now starts with (.venv)
python manage.py runserver
```

Stop the server with **Ctrl + C**. While it's running, it reloads automatically when you save a `.py` file or template. For CSS and JS changes, refresh the browser; use a hard refresh (**⌘⇧R** / **Ctrl+Shift+R**) if it doesn't update.

### After pulling in new code (or unzipping an update)

```bash
source .venv/bin/activate
pip install -r requirements.txt    # only needed if requirements.txt changed
python manage.py migrate           # applies any new database changes; safe to run any time
python manage.py test              # make sure nothing is broken
```

### Optional settings (environment variables)

| Variable | What it does | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL URL (Supabase). Unset = local SQLite | unset |
| `ENV_FILE` | Which env file to load, e.g. `ENV_FILE=.env.production python manage.py migrate` | `.env` |
| `ANTHROPIC_API_KEY` | Turns on **Get AI feedback** in practice mode | off |
| `GITHUB_TOKEN` | Lets commit import read private repos, with a higher rate limit | unset |
| `CRON_SECRET` | Protects the nightly demo-reset endpoint | unset (endpoint disabled) |
| `DEMO_ENABLED` | `0` hides **Try the demo** | `1` |
| `ANTHROPIC_MODEL` | Which model the AI feedback uses | `claude-sonnet-5-5` |
| `SITE_NAME` | Name in the logo and browser tab | `Workbench` |
| `OWNER_NAME` / `OWNER_URL` | Your name and website on the public landing page | `Elaiza Remo` / unset |
| `REPO_URL` | "Source on GitHub" link on the landing page | unset |
| `DJANGO_DEBUG` | `0` turns off debug pages | `1` locally, `0` on Vercel |
| `DJANGO_SECRET_KEY` | Secret key; must be set before deploying | a dev-only key |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames the site answers to | `localhost,127.0.0.1` |

Put them in a `.env` file next to `manage.py` (copy `.env.example`; it's git-ignored), or set one for a single run:

```bash
ANTHROPIC_API_KEY=sk-ant-... python manage.py runserver
```

---

## 2. How the project is organized

Django splits a site into **apps**. Workbench has three, plus the project config:

```
interview-prep/
├── manage.py               # entry point for every command (runserver, migrate, test…)
├── requirements.txt        # Python dependencies (Django, psycopg)
├── vercel.json             # Vercel: function timeout + nightly demo-reset cron
├── .env.example            # copy to .env for local settings (git-ignored)
├── DEPLOY.md               # how to host it on Vercel + Supabase
├── db.sqlite3              # YOUR LOCAL DATA. Created by migrate. Not in git. Back it up.
│
├── config/                 # project-wide setup
│   ├── settings.py         # installed apps, database, SITE_NAME, API key…
│   └── urls.py             # top-level routes: "/", "/prep/", "/projects/", "/admin/"
│
├── core/                   # the site shell, accounts, demo, shared helpers
│   ├── views.py            # Home, login, "Try the demo", nightly demo-reset endpoint
│   ├── ownership.py        # OwnedQuerySet.for_user(): keeps each account's data separate
│   ├── activity.py         # builds the contributions graph
│   ├── demo.py             # sample data for the demo account + reset_demo()
│   ├── accounts.py         # picks the user for management commands
│   ├── testing.py          # LoggedInTestCase for tests
│   ├── utils.py            # confirm_delete() helper used by all delete pages
│   ├── context_processors.py   # puts SITE_NAME, `section` and `is_demo` into every template
│   ├── management/commands/    # claim_data, reset_demo
│   ├── templates/core/
│   │   ├── base.html       # sidebar, tab strip, theme toggle: wraps EVERY page
│   │   ├── landing.html    # public page for signed-out visitors: why, features, demo button
│   │   ├── login.html      # standalone sign-in page
│   │   ├── home.html
│   │   ├── _activity.html  # the contributions graph
│   │   └── confirm_delete.html
│   └── static/core/
│       ├── style.css       # all styling (theme colors at the top)
│       └── tabs.js         # IDE-style tabs
│
├── prep/                   # Interview Prep section  →  /prep/…
│   ├── models.py           # Tag, Project, Story, Question, QuestionSighting, PracticeAttempt
│   ├── views.py            # dashboard, stories, questions, practice, history
│   ├── urls.py             # routes under /prep/
│   ├── forms.py            # StoryForm, QuestionForm, BulkImportForm…
│   ├── srs.py              # spaced repetition: when a question comes back
│   ├── importing.py        # parses pasted question lists, guesses categories
│   ├── ai.py               # optional AI feedback (calls the Anthropic API)
│   ├── management/commands/seed_questions.py
│   ├── templates/prep/     # one HTML file per page, plus _partials
│   ├── static/prep/practice.js   # timer, recording, transcription
│   ├── migrations/         # database change history (don't edit old ones)
│   └── tests.py
│
└── journal/                # Projects section  →  /projects/…
    ├── models.py           # Commit, Note
    ├── views.py            # projects, commits, notes, export, note → story, practice questions
    ├── urls.py             # routes under /projects/
    ├── forms.py            # ProjectForm, NoteForm
    ├── gitsync.py          # reads `git log` from a local repo; picks local vs GitHub
    ├── github.py           # imports commits through the GitHub API
    ├── practice.py         # turns notes into interview practice questions
    ├── management/commands/sync_commits.py
    ├── templates/journal/
    ├── migrations/
    └── tests.py
```

**Rule of thumb for finding things:**

| You want to change… | Look in… |
| --- | --- |
| What a page shows or how it's laid out | `<app>/templates/<app>/<page>.html` |
| What data a page loads, or what a button does | `<app>/views.py` (always via `for_user`, see §4) |
| A page's URL | `<app>/urls.py` |
| Fields on a form | `<app>/forms.py` |
| What's stored in the database | `<app>/models.py` (then make a migration) |
| Colors, fonts, spacing | `core/static/core/style.css` |
| The sidebar, tabs or anything on every page | `core/templates/core/base.html` |

---

## 3. How a page works: URL → view → template

Every page follows the same path. Take **Stories** at `/prep/stories/`:

**1. `config/urls.py`** sends anything starting with `prep/` to the prep app:

```python
path("prep/", include("prep.urls")),
```

**2. `prep/urls.py`** matches the rest of the URL to a view function and gives the route a name:

```python
path("stories/", views.story_list, name="story_list"),
```

**3. `prep/views.py`** loads data and renders a template:

```python
def story_list(request):
    stories = Story.objects.select_related("project").prefetch_related("tags")
    ...
    return render(request, "prep/story_list.html", {"stories": stories, ...})
```

**4. `prep/templates/prep/story_list.html`** turns that data into HTML:

```django
{% extends "prep/base.html" %}          {# wraps the page in the sidebar + tabs #}
{% block title %}Stories{% endblock %}  {# browser tab and IDE tab label #}
{% block content %}
  {% for story in stories %}
    <h2><a href="{{ story.get_absolute_url }}">{{ story.title }}</a></h2>
  {% endfor %}
{% endblock %}
```

### Linking between pages

Never hard-code paths. Use the route **name** with its app prefix:

```django
<a href="{% url 'prep:story_list' %}">Stories</a>
<a href="{% url 'journal:project_detail' project.pk %}">{{ project.name }}</a>
<a href="{% url 'home' %}">Home</a>
```

In Python: `reverse("prep:story_list")` or `redirect("journal:project_detail", pk=project.pk)`.

Most models also have `get_absolute_url()`, so `{{ story.get_absolute_url }}` or `redirect(story)` takes you to that object's page.

### Forms

Create and edit pages share one view and one template. The view checks whether it's a POST and whether the form is valid:

```python
def story_form(request, pk=None):
    story = get_object_or_404(Story, pk=pk) if pk else None   # None means "new"
    form = StoryForm(request.POST or None, instance=story)
    if request.method == "POST" and form.is_valid():
        story = form.save()
        messages.success(request, "Story saved.")             # green banner on the next page
        return redirect(story)
    return render(request, "prep/story_form.html", {"form": form, "story": story})
```

Templates render fields with the shared partial, which handles label, help text and errors:

```django
{% include "prep/_field.html" with field=form.title %}
```

Every POST form needs `{% csrf_token %}` inside it, or Django rejects it with a 403.

### Shared template pieces

| Partial | Use |
| --- | --- |
| `prep/_field.html` | One form field with label, help and errors |
| `prep/_star.html` | A story's S/T/A/R blocks (expects `story`) |
| `prep/_tags.html` | Tag chips (expects `tags` and `link_to`, a URL name) |
| `journal/_note_card.html` | A note in a list (expects `note`; add `show_project=True` to show the project) |

---

## 4. The data model

### Accounts and ownership (read this before writing a query)

Workbench has more than one account: yours, plus the public **demo** account. Every piece of data belongs to one of them:

- `Tag`, `Project`, `Story` and `Question` have an `owner` field.
- Everything else belongs to one of those: `Note` and `Commit` through their project, `PracticeAttempt` and `QuestionSighting` through their question.

Every model's manager has `for_user()`, which follows the right path for you. **In views, always start from it:**

```python
Story.objects.for_user(request.user)                       # ✓ only this account's stories
get_object_or_404(Note.objects.for_user(request.user), pk=pk)   # ✓ 404 for anyone else's note
Story.objects.all()                                        # ✗ would show every account's data
```

When creating objects that have an `owner`, set it: `Story.objects.create(owner=request.user, …)`. Forms take `owner=request.user` too. They stamp new objects with it and limit dropdowns (projects, stories, commits) to that owner's things:

```python
form = StoryForm(request.POST or None, instance=story, owner=request.user)
```

Names are unique *per owner*: two accounts can both have a project called "eFit".

Every page requires a login (Django's `LoginRequiredMiddleware`). The few public views are marked `@login_not_required`: the landing page (`/` when signed out), login, the demo button, and the cron endpoint.

**Editing the landing page:** the "Why I built this" story and feature cards are plain HTML in `core/templates/core/landing.html`. Change the words there.

| Model (app) | Relationship | Access it as |
| --- | --- | --- |
| Project (prep) | has many Stories | `project.stories.all()` |
| Project | has many Notes, Commits | `project.notes.all()`, `project.commits.all()` |
| Project | has many practice Questions | `project.practice_questions.all()` |
| Story ↔ Question | many-to-many | `story.questions.all()`, `question.stories.all()` |
| Question | has many sightings and attempts | `question.sightings.all()`, `question.attempts.all()` |
| Question → Note | made from a note (optional) | `question.source_note`, `note.practice_questions.all()` |
| Note ↔ Commit | many-to-many | `note.commits.all()`, `commit.notes.all()` |
| Note ↔ Story | many-to-many ("turned into story") | `note.stories.all()`, `story.source_notes.all()` |
| Tag | many-to-many with Story, Question, Note | `story.tags.all()`, `tag.stories.all()`, `tag.project_notes.all()` |

- **Project** (`prep/models.py`) is shared: stories and notes both point at it.
- **Story** is a STAR answer. It links to **Questions** many-to-many (`story.questions`, `question.stories`).
- **Question** carries its own spaced-repetition fields (`ease`, `interval_days`, `repetitions`, `due_at`) updated by `prep/srs.py`. Questions generated from the journal have `category="project"`, plus `project` and `source_note`.
- **Note** (`journal/models.py`) has a `kind` (decision, issue, ai, learning, note). All kinds share three text fields (`context`, `details`, `outcome`); `Note.FIELD_LABELS` gives each kind its own labels and prompts.
- **Commit** is imported from git. It's unique per project + SHA, so importing twice never duplicates.

Explore real data at http://127.0.0.1:8000/admin/ after creating a login with `python manage.py createsuperuser`.

### Querying from the shell

`python manage.py shell` opens Python with Django loaded. Handy for poking at data:

```python
from prep.models import Story, Question, Project
from journal.models import Note

Story.objects.count()
Question.objects.filter(category="behavioral", stories__isnull=True)   # questions with no story
Project.objects.get(name="eFit").notes.filter(kind="decision")
Note.objects.filter(ai_tool__iexact="claude").values_list("title", flat=True)
```

---

## 5. Recipes for common changes

### Change wording on a page

Find the text in `<app>/templates/<app>/…html` (search the project for a phrase you can see on screen) and edit it. Save, refresh. Flash messages like "Story saved." live in the view in `views.py`.

### Change a color or the theme

All colors are CSS variables at the top of `core/static/core/style.css`: one block for dark mode (`:root, [data-theme="dark"]`) and one for light (`[data-theme="light"]`). For example, to make the accent green a different color, change `--accent` (and `--btn-bg` for buttons) in both blocks.

### Add a link to the sidebar

Edit the `<nav class="side-nav">` in `core/templates/core/base.html`:

```django
<a href="{% url 'prep:history' %}" {% if section == 'prep' and name == 'history' %}aria-current="page"{% endif %}>History</a>
```

`section` is the app (`home`, `prep` or `journal`) and `name` is the URL name; together they decide which link is highlighted.

### Add a new page

Say you want a **Weekly recap** page at `/projects/recap/`.

1. **View** in `journal/views.py`:

   ```python
   def recap(request):
       week_ago = timezone.localdate() - timedelta(days=7)
       notes = Note.objects.for_user(request.user).filter(happened_on__gte=week_ago).select_related("project")
       return render(request, "journal/recap.html", {"notes": notes})
   ```

   (Add `from datetime import timedelta` at the top.)

2. **URL** in `journal/urls.py`:

   ```python
   path("recap/", views.recap, name="recap"),
   ```

3. **Template** `journal/templates/journal/recap.html`:

   ```django
   {% extends "journal/base.html" %}
   {% block title %}Weekly recap{% endblock %}
   {% block content %}
     <h1>This week</h1>
     <div class="note-stack">
       {% for note in notes %}{% include "journal/_note_card.html" with show_project=True %}{% empty %}<p class="muted">Nothing yet.</p>{% endfor %}
     </div>
   {% endblock %}
   ```

4. **Link** it from the sidebar (recipe above) with `{% url 'journal:recap' %}`.

5. **Test** it in `journal/tests.py`:

   ```python
   def test_recap_loads(self):
       self.assertEqual(self.client.get(reverse("journal:recap")).status_code, 200)
   ```

The page automatically gets the sidebar, theme and an IDE tab, because it extends the base template.

### Add a field to a model

Say you want a **difficulty** on questions.

1. Add the field in `prep/models.py`, inside `class Question`:

   ```python
   difficulty = models.PositiveSmallIntegerField(default=2, help_text="1 easy – 3 hard")
   ```

   New fields need either a `default`, `blank=True` (text) or `null=True`, so existing rows have a value.

2. Create and apply a migration:

   ```bash
   python manage.py makemigrations prep    # writes prep/migrations/0006_….py
   python manage.py migrate
   ```

3. Add it to the form's `fields` list in `prep/forms.py` (`QuestionForm.Meta.fields`) so you can edit it, and show it in the template, e.g. `{{ question.difficulty }}`.

Commit the new migration file along with the model change.

### Add a new kind of journal note

In `journal/models.py`:

1. Add a constant and a choice: `INTERVIEW = "interview"`, then `(INTERVIEW, "Interview debrief")` in `KIND_CHOICES`.
2. Add its labels in `FIELD_LABELS`, e.g. `"context": ("What they asked", "…")`.
3. `python manage.py makemigrations journal && python manage.py migrate` (choices count as a change).
4. Optional: give it a color in `style.css` (copy the `.kind-learning` rule), a question template in `journal/practice.py` (`_note_question`), and a STAR mapping in `STAR_DRAFT` in `journal/views.py`.

### Add starter questions

Add tuples to `STARTER_QUESTIONS` in `prep/management/commands/seed_questions.py`, then run `python manage.py seed_questions`. It skips questions you already have.

### Change how often questions come back

Edit `prep/srs.py`. `schedule()` decides the next `due_at` from your 1–4 rating; `RELEARN_DELAY` is how soon an "Again" comes back. The tests in `prep/tests.py` (`SrsTests`) describe the expected behavior, so update them if you change it on purpose.

---

## 6. The database

Workbench uses **SQLite**: the whole database is the single file `db.sqlite3` in the project folder. It saves the moment you click Save, survives restarts, and stays only on this computer.

### Migrations

A migration is a file describing a change to the database structure. Workflow:

```bash
python manage.py makemigrations       # after changing models.py: writes a new migration file
python manage.py migrate              # applies any migrations not yet applied
python manage.py showmigrations       # lists migrations and whether each is applied [X]
```

- Commit migration files to git.
- Don't edit or delete migrations that have already been applied. Make a new one instead.
- `migrate` keeps your data. It only adds or alters tables and columns.

### Backup and restore

```bash
cp db.sqlite3 ~/Documents/workbench-backup-$(date +%F).sqlite3     # back up
cp ~/Documents/workbench-backup-2026-11-11.sqlite3 db.sqlite3       # restore (server stopped)
```

Or export everything as JSON, which also works across database types:

```bash
python manage.py dumpdata prep journal --indent 2 > backup.json
python manage.py loaddata backup.json
```

### Start fresh (deletes all your data)

```bash
mv db.sqlite3 db.old.sqlite3     # keep the old one, just in case
python manage.py migrate
python manage.py seed_questions
```

### Admin panel

```bash
python manage.py createsuperuser   # once
```

Then visit http://127.0.0.1:8000/admin/ to browse and edit every table. Registrations live in each app's `admin.py`.

---

## 7. Tests

```bash
python manage.py test                                 # everything
python manage.py test prep                            # one app
python manage.py test journal.tests.GitSyncTests      # one test class
python manage.py test journal.tests.JournalPageTests.test_export_markdown   # one test
```

Tests run against a temporary database, never your real data. Run them after every change and before committing.

**Where tests live:** `prep/tests.py` (spaced repetition, forms, pages, importing, sightings, stories), `journal/tests.py` (git import, notes, export, note → story, practice questions) and `core/tests.py` (login, demo isolation, nightly reset, contributions graph, GitHub import, database URL parsing). The git tests create a throwaway repo, so they need `git` installed.

**Writing a test:** subclass `core.testing.LoggedInTestCase`. It gives you `self.user` (a superuser) and a `self.client` that's already signed in. Give owned objects `owner=self.user`:

```python
from django.urls import reverse
from core.testing import LoggedInTestCase
from prep.models import Story

class MyTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.story = Story.objects.create(owner=self.user, title="Demo day")

    def test_story_page_shows_title(self):
        r = self.client.get(self.story.get_absolute_url())
        self.assertContains(r, "Demo day")

    def test_creating_a_story(self):
        r = self.client.post(reverse("prep:story_create"), {"title": "New one"})
        self.assertTrue(Story.objects.filter(title="New one").exists())
```

---

## 8. Front end: styles, theme and tabs

There's no build step: plain HTML templates, one CSS file and a few small JS files.

### `core/static/core/style.css`

Organized top to bottom:

1. **Theme variables**: the dark and light color blocks. Change colors here only.
2. **Base elements**: body, headings, links, code.
3. **Building blocks**: `.card`, `.btn`, `.btn-primary`, `.chip`, `.badge`, `.filters`, form fields, `.grid-2`.
4. **Page sections**: dashboard, stories, questions, practice, importing, journal.
5. **Midnight minimal overrides**: sidebar layout, monospace accents, flat cards.
6. **IDE editor tabs**: tab strip and breadcrumb.

Reuse existing classes before writing new ones. Useful ones: `card`, `btn btn-primary`, `btn btn-small`, `muted`, `small`, `page-head`, `actions`, `grid-2`, `empty`, `filters`, `kind-chip kind-decision`, `status-chip status-active`.

**Light/dark mode:** the toggle sets `data-theme="light"` or `"dark"` on `<html>` and saves it in `localStorage`. Because every rule uses variables, new CSS works in both modes automatically, as long as you use `var(--ink)`, `var(--surface)` and friends instead of hex colors.

### JavaScript

| File | What it does |
| --- | --- |
| `core/static/core/tabs.js` | IDE tabs. Reads the page title from `<title>`, stores open tabs in `localStorage` under `workbench.tabs.v1`, max 10. Pages can opt out with `{% block no_tab %} data-no-tab="1"{% endblock %}`. |
| `prep/static/prep/practice.js` | Practice timer, microphone recording and playback, live transcription (Chrome/Edge), AI feedback request |
| Inline `<script>` in `story_form.html`, `note_form.html`, `note_detail.html`, `question_import.html` | Small page-only behaviors (attach question, relabel note fields, copy Markdown) |

To clear stuck tabs: open the browser console on the site and run `localStorage.removeItem("workbench.tabs.v1")`.

### Page titles

`{% block title %}…{% endblock %}` sets both the browser title and the IDE tab label, so keep it short.

---

## 9. Management commands

| Command | What it does |
| --- | --- |
| `python manage.py runserver` | Start the site at http://127.0.0.1:8000 (`runserver 8001` for another port) |
| `python manage.py migrate` | Apply database changes |
| `python manage.py makemigrations` | Create migration files after editing models |
| `python manage.py test` | Run the test suite |
| `python manage.py createsuperuser` | Create your login |
| `python manage.py claim_data` | Give all un-owned data (from before logins existed) to your account |
| `python manage.py seed_questions` | Load 30 starter questions for your account (skips ones you have) |
| `python manage.py reset_demo` | Wipe the demo account and re-seed its sample data |
| `python manage.py sync_commits` | Import new commits for every project with a repo link or folder |
| `python manage.py sync_commits "eFit"` | Import for one project |
| `python manage.py sync_commits "eFit" --repo ~/code/efit` | Set a project's repo folder (creates the project if needed) |
| `python manage.py shell` | Python prompt with the app loaded |
| `python manage.py dumpdata prep journal --indent 2 > backup.json` | Export all data as JSON |

Commands that act on "your" data take `--user USERNAME` and default to the first superuser. Add `ENV_FILE=.env.production` in front of any command to run it against the hosted database.

Custom commands live in `<app>/management/commands/<name>.py`. Copy `reset_demo.py` as a template for a new one.

---

## 10. Using git with this project

Put the project under version control. It's good practice and it lets the Projects section track Workbench itself.

```bash
cd interview-prep
git init
git add .
git commit -m "Initial commit"
```

`.gitignore` already keeps out `db.sqlite3`, `.venv/` and `__pycache__/`, so your personal data never gets pushed.

Then, in the app: **Projects → New project → "Workbench"**, set **Repo folder** to this folder (run `pwd` here to get the full path), and click **Import new commits**. From then on, log your decisions about the app as you make them.

A good loop for each change:

```bash
git checkout -b weekly-recap        # branch per feature
# …make changes…
python manage.py test               # all green?
git add -A && git commit -m "Add weekly recap page"
```

---

## 11. Troubleshooting

| Problem | Fix |
| --- | --- |
| `zsh: command not found: python` | Use `python3` until the venv is active: `python3 -m venv .venv`, then `source .venv/bin/activate`. |
| `source: no such file or directory: .venv/bin/activate` | The venv doesn't exist in this folder yet. Run `python3 -m venv .venv` first. Check you're in the folder that has `manage.py` (`ls`). |
| `ModuleNotFoundError: No module named 'django'` | The venv isn't active (no `(.venv)` in your prompt). Run `source .venv/bin/activate`, then `pip install -r requirements.txt`. |
| `no such table` / `no such column` | Run `python manage.py migrate`. |
| Your old stories/projects disappeared after the login update | They exist, but have no owner yet. Run `python manage.py claim_data`. |
| Every page sends you to the login page | You're signed out, or your session expired. Sign in again. In tests, use `LoggedInTestCase`. |
| A page 404s for something that exists | It belongs to a different account (e.g. you're in the demo). That's ownership working as intended. |
| `You have N unapplied migration(s)` warning | Same: `python manage.py migrate`. |
| `TemplateDoesNotExist` | Check the template path in the view matches the file, e.g. `"journal/recap.html"` → `journal/templates/journal/recap.html`. |
| `NoReverseMatch` | A `{% url %}` name is misspelled or missing its prefix (`prep:` / `journal:`), or it's missing a required argument like `pk`. |
| `TemplateSyntaxError` | A tag isn't closed (`{% if %}` without `{% endif %}`, etc.). The error page shows the line. |
| 403 "CSRF verification failed" | Add `{% csrf_token %}` inside the `<form method="post">`. |
| CSS/JS change doesn't show | Hard refresh (⌘⇧R). |
| `Error: That port is already in use` | Another server is running. Stop it (Ctrl + C in its terminal) or use `python manage.py runserver 8001`. |
| Commit import: "isn't a git repo" | Point the repo folder at the folder that contains `.git` (the project root). |
| Commit import: "Couldn't find the folder" | Check the path; `~` is fine. Use `pwd` inside the repo to copy the exact path. |
| AI feedback button missing | `ANTHROPIC_API_KEY` isn't set in the terminal that started the server. |
| Microphone won't record | Browsers only allow the mic on `localhost` / `127.0.0.1` or HTTPS, and you must allow access when asked. |
| Weird old tabs | `localStorage.removeItem("workbench.tabs.v1")` in the browser console, then refresh. |

When something breaks, the debug error page (shown while `DJANGO_DEBUG=1`) includes the file and line. The terminal running `runserver` also prints errors.

---

## 12. Going further

**Hosting:** see [DEPLOY.md](DEPLOY.md) for Vercel + Supabase, step by step. Short version: Vercel runs `config/wsgi.py` as one function and serves `/static/` from its CDN; `DATABASE_URL` points at Supabase's transaction pooler; you run migrations from your Mac with `ENV_FILE=.env.production python manage.py migrate`.

**Django docs worth bookmarking:**

- Tutorial: https://docs.djangoproject.com/en/5.2/intro/tutorial01/
- Models and queries: https://docs.djangoproject.com/en/5.2/topics/db/queries/
- Templates: https://docs.djangoproject.com/en/5.2/ref/templates/language/
- Forms: https://docs.djangoproject.com/en/5.2/topics/forms/
- Testing: https://docs.djangoproject.com/en/5.2/topics/testing/overview/
