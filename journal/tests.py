import shutil
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from unittest import skipUnless

from django.core.management import call_command
from django.test import TestCase

from core.testing import LoggedInTestCase
from django.urls import reverse

from prep.models import Project, Question, Story, Tag

from .gitsync import GitError, parse_log, read_log, sync_project
from .models import Commit, Note

HAS_GIT = shutil.which("git") is not None


def make_repo(path, messages):
    def git(*args):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    for i, msg in enumerate(messages):
        (Path(path) / f"f{i}.txt").write_text("line\n" * (i + 1))
        git("add", ".")
        git("commit", "-q", "-m", msg)


class ParseLogTests(LoggedInTestCase):
    def test_parses_records_and_stats(self):
        out = (
            "\x1eabc123\x1fAna\x1f2026-11-10T09:00:00-07:00\x1fFix login\n\nLonger body\x1f\n"
            " 2 files changed, 10 insertions(+), 3 deletions(-)\n"
            "\x1edef456\x1fAna\x1f2026-11-09T09:00:00-07:00\x1fMerge branch\x1f\n"
        )
        a, b = parse_log(out)
        self.assertEqual(a["message"], "Fix login\n\nLonger body")
        self.assertEqual((a["files_changed"], a["insertions"], a["deletions"]), (2, 10, 3))
        self.assertEqual((b["files_changed"], b["insertions"], b["deletions"]), (0, 0, 0))
        self.assertEqual(a["committed_at"].utcoffset().total_seconds(), -7 * 3600)


@skipUnless(HAS_GIT, "git is not installed")
class GitSyncTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        make_repo(self.tmp, ["Initial commit", "Add charts\n\nUsed Recharts"])
        self.project = Project.objects.create(owner=self.user, name="eFit", repo_path=self.tmp)

    def test_read_log(self):
        rows = read_log(self.tmp)
        self.assertEqual([r["message"].split("\n")[0] for r in rows], ["Add charts", "Initial commit"])

    def test_sync_is_incremental(self):
        self.assertEqual(sync_project(self.project), (2, 2))
        self.assertEqual(sync_project(self.project), (0, 2))
        subprocess.run(["git", "-C", self.tmp, "commit", "-q", "--allow-empty", "-m", "Third"], check=True)
        self.assertEqual(sync_project(self.project), (1, 3))
        self.assertEqual(self.project.commits.first().subject, "Third")

    def test_bad_paths(self):
        with self.assertRaises(GitError):
            read_log("/definitely/not/here")
        not_repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, not_repo, ignore_errors=True)
        with self.assertRaisesMessage(GitError, "isn't a git repo"):
            read_log(not_repo)

    def test_sync_button(self):
        r = self.client.post(reverse("journal:project_sync", args=[self.project.pk]), follow=True)
        self.assertContains(r, "Imported 2 new commits")
        self.assertContains(r, "Add charts")

    def test_command_creates_project(self):
        out = StringIO()
        call_command("sync_commits", "Brand New", "--repo", self.tmp, stdout=out)
        self.assertIn("imported 2 new commit", out.getvalue())
        self.assertEqual(Project.objects.get(name="Brand New").commits.count(), 2)


class JournalPageTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(owner=self.user, name="Workbench", repo_url="https://github.com/me/workbench.git")
        self.commit = Commit.objects.create(
            project=self.project, sha="a" * 40, message="Switch to SQLite\n\nSimpler for MVP",
            committed_at="2026-11-01T10:00:00Z", files_changed=3, insertions=20, deletions=4,
        )
        self.note = Note.objects.create(
            project=self.project, kind=Note.DECISION, title="Chose SQLite",
            context="Needed a DB fast", details="Postgres, SQLite", outcome="SQLite: zero setup",
        )
        self.note.commits.add(self.commit)

    def test_pages_load(self):
        urls = [
            reverse("journal:project_list"),
            reverse("journal:project_create"),
            reverse("journal:project_update", args=[self.project.pk]),
            reverse("journal:project_delete", args=[self.project.pk]),
            reverse("journal:note_list"),
            reverse("journal:note_create"),
            reverse("journal:note_detail", args=[self.note.pk]),
            reverse("journal:note_update", args=[self.note.pk]),
            reverse("journal:note_delete", args=[self.note.pk]),
            reverse("journal:commit_detail", args=[self.commit.pk]),
            reverse("home"),
        ]
        for tab in ("notes", "commits", "stories"):
            urls.append(reverse("journal:project_detail", args=[self.project.pk]) + f"?tab={tab}")
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_commit_remote_link(self):
        self.assertEqual(self.commit.remote_url, "https://github.com/me/workbench/commit/" + "a" * 40)

    def test_note_labels_depend_on_kind(self):
        r = self.client.get(reverse("journal:note_create"), {"project": self.project.pk, "kind": "issue"})
        self.assertContains(r, "What went wrong")
        self.assertContains(r, 'value="issue"')

    def test_create_note_from_commit(self):
        r = self.client.get(reverse("journal:note_create"), {"commit": self.commit.pk})
        self.assertContains(r, "Switch to SQLite")
        r = self.client.post(reverse("journal:note_create"), {
            "project": self.project.pk, "kind": "ai", "title": "Claude wrote the migration",
            "happened_on": "2026-11-02", "ai_tool": "Claude", "context": "Migration",
            "commits": [self.commit.pk], "tags_text": "databases, ai",
        })
        note = Note.objects.get(title="Claude wrote the migration")
        self.assertRedirects(r, note.get_absolute_url())
        self.assertEqual(list(note.commits.all()), [self.commit])
        self.assertEqual(sorted(t.name for t in note.tags.all()), ["ai", "databases"])

    def test_cannot_link_commit_from_other_project(self):
        other = Project.objects.create(owner=self.user, name="Other")
        r = self.client.post(reverse("journal:note_create"), {
            "project": other.pk, "kind": "note", "title": "X", "happened_on": "2026-11-02",
            "commits": [self.commit.pk],
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Note.objects.filter(title="X").exists())

    def test_filters(self):
        Note.objects.create(project=self.project, kind=Note.ISSUE, title="Login loop")
        r = self.client.get(reverse("journal:note_list"), {"kind": "issue"})
        self.assertContains(r, "Login loop")
        self.assertNotContains(r, "Chose SQLite")
        r = self.client.get(reverse("journal:note_list"), {"q": "Simpler for MVP"})  # matches commit message
        self.assertContains(r, "Chose SQLite")

    def test_export_markdown(self):
        r = self.client.get(reverse("journal:note_export"), {"project": self.project.pk, "kind": "decision"})
        self.assertEqual(r["Content-Type"], "text/markdown; charset=utf-8")
        self.assertIn("attachment;", r["Content-Disposition"])
        body = r.content.decode()
        self.assertIn("# Workbench · Decision", body)
        self.assertIn("**What you chose and why**", body)
        self.assertIn("`aaaaaaa` Switch to SQLite", body)

    def test_turn_note_into_story(self):
        self.note.tags.add(Tag.objects.create(owner=self.user, name="databases"))
        r = self.client.post(reverse("journal:note_to_story", args=[self.note.pk]))
        story = Story.objects.get()
        self.assertRedirects(r, reverse("prep:story_update", args=[story.pk]))
        self.assertEqual((story.title, story.project, story.situation, story.action),
                         ("Chose SQLite", self.project, "Needed a DB fast", "SQLite: zero setup"))
        self.assertIn("Options considered", story.brainstorm)
        self.assertEqual([t.name for t in story.tags.all()], ["databases"])
        self.assertEqual(list(self.note.stories.all()), [story])

    def test_delete_project_keeps_stories(self):
        story = Story.objects.create(owner=self.user, title="S", project=self.project)
        self.client.post(reverse("journal:project_delete", args=[self.project.pk]))
        story.refresh_from_db()
        self.assertIsNone(story.project)
        self.assertFalse(Note.objects.exists())
        self.assertFalse(Commit.objects.exists())

    def test_project_form_sets_repo(self):
        self.client.post(reverse("journal:project_create"), {
            "name": "Shelf", "status": "active", "repo_path": "~/code/shelf",
        })
        self.assertEqual(Project.objects.get(name="Shelf").repo_path, "~/code/shelf")


class ProjectQuestionTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(owner=self.user, name="eFit", tech_stack="Next.js, TypeScript")
        self.decision = Note.objects.create(
            project=self.project, kind=Note.DECISION, title="Switched charts to Recharts.",
            context="Chart.js fought React re-renders", outcome="Recharts is React-native",
        )
        self.ai = Note.objects.create(project=self.project, kind=Note.AI, title="Generated Strava types", ai_tool="Claude")
        self.loose = Note.objects.create(project=self.project, kind=Note.NOTE, title="Random thought")
        self.story = Story.objects.create(owner=self.user, title="Charts rewrite", project=self.project)
        self.decision.stories.add(self.story)
        self.url = reverse("journal:project_questions", args=[self.project.pk])

    def test_suggestions(self):
        from .practice import suggest_questions
        texts = [s["text"] for s in suggest_questions(self.project)]
        self.assertIn("On eFit, you decided “Switched charts to Recharts”. Why, and what alternatives did you consider?", texts)
        self.assertIn("Why did you choose Next.js, TypeScript for eFit?", texts)
        self.assertTrue(any("you used Claude for “Generated Strava types”" in t for t in texts))
        self.assertTrue(any("How did you use AI tools while building eFit" in t for t in texts))
        self.assertFalse(any("Random thought" in t for t in texts))  # plain notes left out

    def test_preview_then_add(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Switched charts to Recharts")
        rows = [s for s in r.context["suggestions"]]
        data = {
            "row_text": [s["text"] for s in rows],
            "row_note": [s["note"].pk if s["note"] else "" for s in rows],
            "row_include": [str(i) for i in range(len(rows))],
        }
        r = self.client.post(self.url, data)
        self.assertRedirects(r, reverse("prep:practice") + f"?project={self.project.pk}", fetch_redirect_response=False)
        q = Question.objects.get(source_note=self.decision)
        self.assertEqual((q.category, q.project), (Question.PROJECT, self.project))
        self.assertEqual(list(q.stories.all()), [self.story])
        n = Question.objects.count()

        # Second visit: everything flagged as existing and unticked; re-posting adds nothing.
        r = self.client.get(self.url)
        self.assertTrue(all(s["existing"] for s in r.context["suggestions"]))
        self.client.post(self.url, data)
        self.assertEqual(Question.objects.count(), n)

    def test_single_note_mode(self):
        r = self.client.get(self.url, {"note": self.ai.pk})
        self.assertEqual(len(r.context["suggestions"]), 1)
        self.client.post(self.url, {
            "note": self.ai.pk, "row_text": ["How did you check the types Claude generated?"],
            "row_note": [str(self.ai.pk)], "row_include": ["0"],
        })
        self.assertEqual(Question.objects.get().text, "How did you check the types Claude generated?")

    def test_practice_shows_source_note_and_filters_by_project(self):
        q = Question.objects.create(owner=self.user, text="Why Recharts?", category=Question.PROJECT, project=self.project, source_note=self.decision)
        Question.objects.create(owner=self.user, text="Some unrelated question here")
        for _ in range(4):
            r = self.client.get(reverse("prep:practice"), {"project": self.project.pk, "mode": "random"})
            self.assertContains(r, "Why Recharts?")
        self.assertContains(r, "From your project notes")
        self.assertContains(r, "Chart.js fought React re-renders")
        r = self.client.get(reverse("prep:question_list"), {"project": self.project.pk})
        self.assertContains(r, "Why Recharts?")
        self.assertNotContains(r, "Some unrelated question here")
        self.assertContains(self.client.get(q.get_absolute_url()), "From your project")

    def test_deleting_note_keeps_question(self):
        q = Question.objects.create(owner=self.user, text="Why Recharts?", category=Question.PROJECT, project=self.project, source_note=self.decision)
        self.decision.delete()
        q.refresh_from_db()
        self.assertIsNone(q.source_note)
