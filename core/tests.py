import json
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.settings import _database_from_url
from core import activity
from core.demo import get_demo_user, reset_demo
from core.testing import LoggedInTestCase
from journal import github
from journal.gitsync import GitError, can_sync, sync_project
from journal.models import Commit, Note
from prep.forms import StoryForm
from prep.models import PracticeAttempt, Project, Question, Story

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("elaiza", password="a-strong-password-123")

    def test_signed_out_home_is_the_public_landing_page(self):
        r = self.client.get(reverse("home"))
        self.assertTemplateUsed(r, "core/landing.html")
        self.assertContains(r, "Why I built it")
        self.assertContains(r, "Try the live demo")
        self.assertNotContains(r, "Top secret")

    def test_landing_shows_demo_graph_once_seeded(self):
        self.assertNotContains(self.client.get(reverse("home")), "live from the demo")
        reset_demo()
        self.assertContains(self.client.get(reverse("home")), "live from the demo")

    @override_settings(DEMO_ENABLED=False)
    def test_landing_without_demo(self):
        r = self.client.get(reverse("home"))
        self.assertNotContains(r, "Try the live demo")
        self.assertContains(r, "Sign in")

    def test_every_page_needs_login(self):
        for url in (reverse("prep:story_list"), reverse("journal:project_list"),
                    reverse("journal:note_export"), reverse("prep:practice")):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertRedirects(r, f"{reverse('login')}?next={url}", fetch_redirect_response=False)

    def test_login_and_logout(self):
        self.assertContains(self.client.get(reverse("login")), "Try the demo")
        r = self.client.post(reverse("login"), {"username": "elaiza", "password": "a-strong-password-123"})
        self.assertRedirects(r, reverse("home"))
        self.assertContains(self.client.get(reverse("home")), "contributions in the last year")
        r = self.client.post(reverse("logout"))
        self.assertRedirects(r, reverse("home"))
        self.assertTemplateUsed(self.client.get(reverse("home")), "core/landing.html")
        self.assertEqual(self.client.get(reverse("prep:dashboard")).status_code, 302)

    def test_wrong_password(self):
        r = self.client.post(reverse("login"), {"username": "elaiza", "password": "nope"})
        self.assertContains(r, "didn't match")

    def test_signed_in_user_skips_login_page(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("login")), reverse("home"))

    @override_settings(DEMO_ENABLED=False)
    def test_demo_can_be_turned_off(self):
        self.assertNotContains(self.client.get(reverse("login")), "Try the demo")
        self.assertRedirects(self.client.post(reverse("demo_login")), reverse("login"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username="demo").exists())


class DemoTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("elaiza", password="a-strong-password-123")
        self.secret = Project.objects.create(owner=self.owner, name="Top secret project")
        self.secret_story = Story.objects.create(owner=self.owner, title="My private story")

    def enter_demo(self):
        r = self.client.post(reverse("demo_login"), follow=True)
        self.assertContains(r, "Demo mode.")
        return get_demo_user()

    def test_demo_has_sample_data_in_every_section(self):
        demo = self.enter_demo()
        self.assertGreaterEqual(Project.objects.for_user(demo).count(), 3)
        self.assertGreater(Commit.objects.for_user(demo).count(), 50)
        self.assertGreater(Note.objects.for_user(demo).count(), 5)
        self.assertGreater(Story.objects.for_user(demo).count(), 1)
        self.assertGreater(PracticeAttempt.objects.for_user(demo).count(), 20)
        self.assertTrue(Question.objects.for_user(demo).filter(category=Question.PROJECT).exists())
        home = self.client.get(reverse("home"))
        self.assertGreater(home.context["graph"]["total"], 100)
        for url in (reverse("prep:dashboard"), reverse("prep:story_list"), reverse("prep:question_list"),
                    reverse("prep:practice"), reverse("prep:history"), reverse("journal:project_list"),
                    reverse("journal:note_list")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_demo_cannot_see_real_data(self):
        self.enter_demo()
        self.assertNotContains(self.client.get(reverse("journal:project_list")), "Top secret project")
        self.assertNotContains(self.client.get(reverse("prep:story_list")), "My private story")
        self.assertEqual(self.client.get(reverse("journal:project_detail", args=[self.secret.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("prep:story_detail", args=[self.secret_story.pk])).status_code, 404)
        r = self.client.post(reverse("prep:story_delete", args=[self.secret_story.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Story.objects.filter(pk=self.secret_story.pk).exists())

    def test_real_account_cannot_see_demo_data(self):
        demo = reset_demo()
        demo_project = Project.objects.for_user(demo).first()
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(reverse("journal:project_list")), demo_project.name)
        self.assertEqual(self.client.get(demo_project.get_absolute_url()).status_code, 404)

    def test_demo_cannot_attach_someone_elses_project(self):
        demo = self.enter_demo()
        form = StoryForm(data={"title": "Sneaky", "project": self.secret.pk}, owner=demo)
        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    @override_settings(ANTHROPIC_API_KEY="sk-test")
    def test_demo_has_no_ai_feedback_or_commit_import(self):
        demo = self.enter_demo()
        q = Question.objects.for_user(demo).first()
        self.assertNotContains(self.client.get(reverse("prep:practice"), {"question": q.pk}), "Get AI feedback")
        r = self.client.post(reverse("prep:practice_feedback", args=[q.pk]), {"answer": "hi"})
        self.assertEqual(r.status_code, 400)
        project = Project.objects.for_user(demo).exclude(repo_url="").first()
        self.assertFalse(can_sync(project, demo))
        r = self.client.post(reverse("journal:project_sync", args=[project.pk]), follow=True)
        self.assertContains(r, "available for this project")

    def test_reset_wipes_visitor_changes(self):
        demo = self.enter_demo()
        Project.objects.create(owner=demo, name="Visitor scribble")
        reset_demo()
        self.assertFalse(Project.objects.filter(name="Visitor scribble").exists())
        self.assertTrue(Project.objects.filter(pk=self.secret.pk).exists())  # real data untouched

    @override_settings(CRON_SECRET="s3cret")
    def test_cron_endpoint_needs_the_secret(self):
        url = reverse("cron_reset_demo")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION="Bearer wrong").status_code, 403)
        r = self.client.get(url, HTTP_AUTHORIZATION="Bearer s3cret")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertTrue(Project.objects.for_user(get_demo_user()).exists())

    @override_settings(CRON_SECRET="")
    def test_cron_endpoint_disabled_without_secret(self):
        self.assertEqual(self.client.get(reverse("cron_reset_demo"), HTTP_AUTHORIZATION="Bearer ").status_code, 403)

    def test_reset_demo_command(self):
        out = StringIO()
        call_command("reset_demo", stdout=out)
        self.assertIn("reset", out.getvalue())


class OwnershipTests(LoggedInTestCase):
    def test_same_name_allowed_for_different_users_but_not_twice_for_one(self):
        other = User.objects.create_user("someone")
        Project.objects.create(owner=other, name="eFit")
        r = self.client.post(reverse("journal:project_create"), {"name": "eFit", "status": "active"})
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse("journal:project_create"), {"name": "eFit", "status": "active"})
        self.assertContains(r, "You already have a project with this name.")

    def test_claim_data_gives_orphans_to_the_superuser(self):
        orphan = Project.objects.create(name="From before logins")
        Question.objects.create(text="Old question?")
        out = StringIO()
        call_command("claim_data", stdout=out)
        orphan.refresh_from_db()
        self.assertEqual(orphan.owner, self.user)
        self.assertEqual(Question.objects.get(text="Old question?").owner, self.user)
        self.assertContains(self.client.get(reverse("journal:project_list")), "From before logins")


class ActivityGraphTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.today = date(2026, 11, 11)  # a Wednesday
        self.project = Project.objects.create(owner=self.user, name="eFit")
        tz = timezone.get_current_timezone()

        def at(d, hour=12):
            return timezone.make_aware(datetime(d.year, d.month, d.day, hour), tz)

        for i in range(3):
            Commit.objects.create(project=self.project, sha=f"{i:040x}", message="x", committed_at=at(self.today))
        Commit.objects.create(project=self.project, sha="f" * 40, message="x", committed_at=at(self.today - timedelta(days=1)))
        Note.objects.create(project=self.project, title="n", happened_on=self.today - timedelta(days=1))
        q = Question.objects.create(owner=self.user, text="Why?")
        a = PracticeAttempt.objects.create(question=q, rating=3)
        PracticeAttempt.objects.filter(pk=a.pk).update(created_at=at(self.today - timedelta(days=10)))
        # someone else's activity must not count
        other = Project.objects.create(owner=User.objects.create_user("x"), name="theirs")
        Commit.objects.create(project=other, sha="e" * 40, message="x", committed_at=at(self.today))

    def test_counts_levels_and_labels(self):
        g = activity.build(self.user, today=self.today)
        self.assertEqual(len(g["columns"]), 53)
        cells = {c["date"]: c for week in g["columns"] for c in week if c}
        self.assertEqual(cells["2026-11-11"]["total"], 3)
        self.assertEqual(cells["2026-11-11"]["label"], "3 commits on Wednesday, Nov 11, 2026")
        self.assertEqual(cells["2026-11-10"]["label"], "1 commit, 1 note on Tuesday, Nov 10, 2026")
        self.assertEqual(cells["2026-11-02"]["level"], 0)
        self.assertEqual(cells["2026-11-01"]["label"], "1 practice run on Sunday, Nov 1, 2026")
        self.assertEqual(cells["2026-11-11"]["level"], 4)
        self.assertEqual(g["total"], 3 + 2 + 1 + 0)  # stories created "now" fall outside this fixed date
        self.assertEqual(g["current_streak"], 2)
        self.assertEqual(g["longest_streak"], 2)
        self.assertEqual({b["key"]: b["count"] for b in g["breakdown"]}["commits"], 4)

    def test_grid_shape(self):
        g = activity.build(self.user, today=self.today)
        last_week = g["columns"][-1]
        self.assertEqual(last_week[0]["date"], "2026-11-08")  # weeks start on Sunday
        self.assertIsNone(last_week[4])  # Thursday is in the future
        self.assertTrue(g["months"])

    def test_home_shows_graph(self):
        r = self.client.get(reverse("home"))
        self.assertContains(r, "contributions in the last year")
        self.assertContains(r, 'class="ag-cell')


class _FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _gh_commit(i, day):
    return {
        "sha": f"{i:040x}",
        "author": {"login": "elaiza-remo"},
        "commit": {"message": f"Commit {i}\n\nBody", "author": {"name": "Elaiza Remo", "date": f"2026-11-{day:02d}T10:00:00Z"}},
    }


class GitHubImportTests(LoggedInTestCase):
    def test_parse_repo(self):
        for url, expected in [
            ("https://github.com/elaiza-remo/Shelf", ("elaiza-remo", "Shelf")),
            ("https://github.com/elaiza-remo/Shelf.git", ("elaiza-remo", "Shelf")),
            ("https://github.com/elaiza-remo/Shelf/", ("elaiza-remo", "Shelf")),
            ("git@github.com:elaiza-remo/my.repo.git", ("elaiza-remo", "my.repo")),
            ("https://gitlab.com/a/b", None),
            ("", None),
        ]:
            with self.subTest(url=url):
                self.assertEqual(github.parse_repo(url), expected)

    def test_fetch_paginates_and_sync_is_incremental(self):
        project = Project.objects.create(owner=self.user, name="Shelf", repo_url="https://github.com/elaiza-remo/Shelf")
        page1 = [_gh_commit(i, 10) for i in range(100)]
        page2 = [_gh_commit(100 + i, 9) for i in range(5)]
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            page = 2 if "page=2" in req.full_url else 1
            return _FakeResponse(json.dumps(page1 if page == 1 else page2).encode())

        with mock.patch("journal.github.urllib.request.urlopen", side_effect=fake_urlopen):
            self.assertTrue(can_sync(project, self.user))
            self.assertEqual(sync_project(project), (105, 105))
        self.assertEqual(len(calls), 2)
        self.assertIn("/repos/elaiza-remo/Shelf/commits", calls[0])
        c = project.commits.get(sha=f"{0:040x}")
        self.assertEqual((c.subject, c.author), ("Commit 0", "Elaiza Remo"))
        self.assertEqual(c.committed_at, datetime(2026, 11, 10, 10, tzinfo=dt_timezone.utc))

        # Second import asks only for commits since the newest one and skips duplicates.
        with mock.patch("journal.github.urllib.request.urlopen",
                        return_value=_FakeResponse(json.dumps([_gh_commit(0, 10)]).encode())) as m:
            self.assertEqual(sync_project(project), (0, 1))
        self.assertIn("since=", m.call_args[0][0].full_url)

    @override_settings(GITHUB_TOKEN="ghp_test")
    def test_token_is_sent(self):
        project = Project.objects.create(owner=self.user, name="P", repo_url="https://github.com/a/b")
        with mock.patch("journal.github.urllib.request.urlopen", return_value=_FakeResponse(b"[]")) as m:
            sync_project(project)
        self.assertEqual(m.call_args[0][0].get_header("Authorization"), "Bearer ghp_test")

    def test_not_found_message(self):
        import urllib.error

        project = Project.objects.create(owner=self.user, name="P", repo_url="https://github.com/a/missing")
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch("journal.github.urllib.request.urlopen", side_effect=err):
            with self.assertRaisesMessage(GitError, "couldn't find that repo"):
                sync_project(project)

    def test_missing_local_folder_explains_what_to_do(self):
        project = Project.objects.create(owner=self.user, name="P", repo_path="/not/on/this/machine")
        self.assertFalse(can_sync(project, self.user))
        with self.assertRaisesMessage(GitError, "set the project's GitHub repo link"):
            sync_project(project)


class DatabaseUrlTests(TestCase):
    def test_supabase_transaction_pooler(self):
        db = _database_from_url("postgresql://postgres.abc123:p%40ss@aws-0-ca-central-1.pooler.supabase.com:6543/postgres")
        self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((db["USER"], db["PASSWORD"], db["PORT"]), ("postgres.abc123", "p@ss", 6543))
        self.assertTrue(db["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertEqual(db["CONN_MAX_AGE"], 0)
        self.assertIsNone(db["OPTIONS"]["prepare_threshold"])
        self.assertEqual(db["OPTIONS"]["sslmode"], "require")

    def test_session_pooler_for_migrations(self):
        db = _database_from_url("postgres://postgres.abc123:pw@aws-0-ca-central-1.pooler.supabase.com:5432/postgres")
        self.assertFalse(db["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertNotIn("prepare_threshold", db["OPTIONS"])

    def test_rejects_other_schemes(self):
        with self.assertRaises(RuntimeError):
            _database_from_url("mysql://x@y/z")
