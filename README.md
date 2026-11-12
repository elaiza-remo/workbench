# Workbench

A personal Django site for a developer's job search and side projects. It has two sections:

- **Interview Prep**: a STAR story bank, a question library and timed practice with spaced repetition.
- **Projects**: a project journal for logging decisions, issues, AI usage and lessons as you build, linked to your git commits, so you have specific answers ready when an interviewer asks "why did you build it that way?"

The two share one project list. Any journal note can be turned into a STAR interview story with one click.

## Features

**Accounts, demo and hosting**
- Public landing page explaining why the app exists and what it does, with a **Try the live demo** button
- Sign-in page; only your account can see your data
- **Try the demo**: a sandbox account with a year of realistic sample data that visitors can explore and edit, reset every night
- Home page **contributions graph** (like GitHub's) counting commits, notes, practice runs and stories per day, with streaks and a per-day breakdown on hover
- Runs locally on SQLite, or hosted on **Vercel + Supabase** (see [DEPLOY.md](DEPLOY.md))

**Interface**
- Dark "midnight" theme with a light mode switch, a sidebar, and IDE-style tabs: every page you open becomes a tab you can switch between or close (×, or middle-click). Tabs are remembered in your browser. A dot on a tab means a form on it has unsaved changes.

**Projects (journal)**
- Projects with status, tech stack, start date, repo folder and repo link
- Notes in five kinds, each with its own prompts:
  - **Decision**: the problem, options considered, what you chose and why
  - **Issue & fix**: what went wrong, what you tried, the fix and root cause
  - **AI usage**: which tool, what you used it for, what it gave you, what you kept or changed
  - **Learning** and general **Note**
- Import commits from GitHub (on the hosted site) or a local git repo (when running on your Mac) with one button or `python manage.py sync_commits`
- Link notes to commits, and see every note on a commit's page
- Filter all notes by kind, project, tag or AI tool; search covers note text and commit messages
- Export any filtered set of notes as a Markdown file, or copy a single note as Markdown
- **Turn into interview story**: drafts a STAR story from a note and links the two
- **Practice questions**: generates the questions an interviewer would ask about a project from its notes ("On eFit, you decided X. Why, and what alternatives did you consider?"). You edit them, add them to practice mode, and the original note appears when you reveal your answer.


**Story bank**
- Write stories in STAR format (Situation, Task, Action, Result), with a flag on any story missing a part
- A brainstorm area beside the STAR fields for rough notes, with prompts if you're stuck
- Attach the question you're answering so it stays pinned at the top while you write ("Write a story for this" on any question does it for you)
- Tag stories by theme (conflict, failure, leadership…) and group them by project
- Search and filter by text, tag or project
- Dashboard shows gaps: behavioural questions with no story, incomplete stories, and themes you haven't covered

**Question library**
- Behavioural, technical and general questions, each with notes and linked stories
- **Paste questions**: paste a list from an application, interview notes or an email. Bullets, numbering and `Q1:` prefixes are stripped, wrapped lines are rejoined, and each question's category is auto-detected. You review and edit everything in a preview before it's saved.
- **Where you've seen it**: log each time a question comes up (interview or application, company, date). Pasting a question you already have logs another sighting instead of creating a duplicate.
- Filter by where you saw a question, search by company, and sort by "most seen" to find the questions that keep coming up
- `seed_questions` loads 30 common questions to start from

**Practice mode**
- Pulls the next question that's due for review, or a random one, filtered by category, tag, or only questions you've actually been asked
- Timer (turns amber past 2 minutes on behavioural questions)
- Record your answer and play it back in the browser; nothing is uploaded or stored
- Live transcription while recording in Chrome and Edge, via the browser's speech recognition
- Reveal your notes and linked STAR stories after you answer, to check yourself
- Rate yourself Again / Hard / Good / Easy; a simplified SM-2 algorithm schedules the next review
- Optional AI feedback on your answer (see below)
- History page and a day-streak counter

## Getting started

For a full walkthrough of the code, how to make changes, and troubleshooting, see **[DEVELOPER.md](DEVELOPER.md)**.

Requires Python 3.10+.

```bash
python3 -m venv .venv            # macOS/Linux; on Windows use: python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # your login
python manage.py seed_questions    # optional starter questions
python manage.py runserver
```

Then open http://127.0.0.1:8000. Interview Prep lives at `/prep/` and Projects at `/projects/`.

Run the tests with:

```bash
python manage.py test
```

Django's admin panel is at `/admin/` (sign in with the same account).

## Importing commits

Set a project's **Repo folder** (e.g. `~/code/efit`) on its edit page, then click **Import new commits** on its Commits tab. Running it again only adds commits you don't have yet.

From the terminal:

```bash
python manage.py sync_commits                                 # every project with a repo folder
python manage.py sync_commits "eFit"                          # one project
python manage.py sync_commits "eFit" --repo ~/code/efit       # set the folder (creates the project if needed)
```

Commits come from the repo's current branch.

## Optional: AI feedback

Set an Anthropic API key before starting the server and a **Get AI feedback**
button appears in practice mode. It checks your typed or transcribed answer
against STAR and suggests improvements.

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python manage.py runserver
```

`ANTHROPIC_MODEL` overrides the model if you want a different one.

## Project layout

```
config/            Django settings and root URLs
core/              Site shell: home page, shared layout, styles
journal/
  models.py        Commit, Note
  gitsync.py       Reads `git log` from a local repo
  views.py         Projects, commits, notes, Markdown export, note → story
  management/commands/sync_commits.py
prep/
  models.py        Tag, Project (shared), Story, Question, QuestionSighting, PracticeAttempt
  importing.py     Parses pasted questions and guesses categories
  srs.py           Spaced repetition scheduling
  ai.py            Optional AI feedback (standard library only)
  forms.py         Forms, including comma-separated tag entry
  views.py         Function-based views
  templates/prep/  HTML templates
  static/prep/     Practice-mode JavaScript
  management/commands/seed_questions.py
  tests.py
```

## Notes

- The site name in the header comes from `SITE_NAME` in `config/settings.py` (default "Workbench").
- Single-user and meant to run locally; there's no login. Add Django's auth
  (`LoginRequiredMixin` / `@login_required`) and a `user` foreign key on each
  model before hosting it publicly.
- Before deploying, set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0` and
  `DJANGO_ALLOWED_HOSTS`.
- Microphone recording needs `localhost` or HTTPS, which browsers require for mic access.
