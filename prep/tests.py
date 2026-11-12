from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.testing import LoggedInTestCase
from django.urls import reverse
from django.utils import timezone

from . import importing, srs
from .forms import QuestionForm, StoryForm, parse_tags
from .models import PracticeAttempt, Project, Question, QuestionSighting, Story, Tag
from .views import practice_streak


class SrsTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now()
        self.q = Question(text="Q")

    def test_again_resets_and_comes_back_soon(self):
        self.q.repetitions, self.q.interval_days = 3, 10
        srs.schedule(self.q, 1, now=self.now)
        self.assertEqual(self.q.repetitions, 0)
        self.assertEqual(self.q.interval_days, 0)
        self.assertEqual(self.q.due_at, self.now + srs.RELEARN_DELAY)
        self.assertLess(self.q.ease, 2.5)

    def test_good_answers_space_out(self):
        intervals = []
        for _ in range(4):
            srs.schedule(self.q, 3, now=self.now)
            intervals.append(self.q.interval_days)
        self.assertEqual(intervals[:2], [1, 4])
        self.assertTrue(intervals[2] > intervals[1] and intervals[3] > intervals[2])

    def test_easy_beats_hard(self):
        hard, easy = Question(text="h"), Question(text="e")
        for q, r in ((hard, 2), (easy, 4)):
            for _ in range(3):
                srs.schedule(q, r, now=self.now)
        self.assertGreater(easy.interval_days, hard.interval_days)

    def test_ease_has_a_floor(self):
        for _ in range(20):
            srs.schedule(self.q, 1, now=self.now)
        self.assertGreaterEqual(self.q.ease, srs.MIN_EASE)

    def test_bad_rating_rejected(self):
        with self.assertRaises(ValueError):
            srs.schedule(self.q, 5)


class FormTests(LoggedInTestCase):
    def test_parse_tags_normalises_and_dedupes(self):
        self.assertEqual(parse_tags(" Conflict, teamwork,conflict ,, "), ["conflict", "teamwork"])

    def test_story_form_creates_tags_and_new_project(self):
        form = StoryForm(data={"title": "Demo day", "action": "I fixed it", "tags_text": "deadline, Teamwork", "new_project": "Capstone"}, owner=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        story = form.save()
        self.assertEqual(story.project.name, "Capstone")
        self.assertEqual(sorted(t.name for t in story.tags.all()), ["deadline", "teamwork"])

    def test_editing_tags_replaces_them(self):
        story = Story.objects.create(owner=self.user, title="S")
        story.tags.add(Tag.objects.create(owner=self.user, name="old"))
        form = StoryForm(data={"title": "S", "tags_text": "new"}, instance=story, owner=self.user)
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual([t.name for t in story.tags.all()], ["new"])

    def test_question_form_links_stories(self):
        story = Story.objects.create(owner=self.user, title="S")
        form = QuestionForm(data={"text": "Why?", "category": "behavioral", "stories": [story.pk]}, owner=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.save().stories.all()), [story])


class StoryModelTests(LoggedInTestCase):
    def test_missing_parts(self):
        s = Story(title="x", situation="a", action="b")
        self.assertEqual(s.missing_parts, ["task", "result"])
        self.assertFalse(s.is_complete)


class PageTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(owner=self.user, name="Capstone")
        self.story = Story.objects.create(owner=self.user, title="Fixing the deploy", project=self.project, situation="s", task="t", action="a", result="r")
        self.question = Question.objects.create(owner=self.user, text="Tell me about a challenge.")
        self.question.stories.add(self.story)

    def test_pages_load(self):
        urls = [
            reverse("prep:dashboard"),
            reverse("prep:story_list"), reverse("prep:story_create"),
            reverse("prep:story_detail", args=[self.story.pk]), reverse("prep:story_update", args=[self.story.pk]),
            reverse("prep:story_delete", args=[self.story.pk]),
            reverse("prep:question_list"), reverse("prep:question_create"),
            reverse("prep:question_detail", args=[self.question.pk]), reverse("prep:question_update", args=[self.question.pk]),
            reverse("journal:project_list"), reverse("journal:project_detail", args=[self.project.pk]),
            reverse("home"),
            reverse("prep:practice"), reverse("prep:history"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_filters(self):
        self.story.tags.add(Tag.objects.create(owner=self.user, name="conflict"))
        r = self.client.get(reverse("prep:story_list"), {"tag": "conflict", "q": "deploy"})
        self.assertContains(r, "Fixing the deploy")
        r = self.client.get(reverse("prep:story_list"), {"q": "nonexistent"})
        self.assertNotContains(r, "Fixing the deploy")

    def test_create_story(self):
        r = self.client.post(reverse("prep:story_create"), {"title": "New one", "tags_text": "failure"})
        story = Story.objects.get(title="New one")
        self.assertRedirects(r, story.get_absolute_url())

    def test_delete_requires_post(self):
        self.client.get(reverse("prep:story_delete", args=[self.story.pk]))
        self.assertTrue(Story.objects.filter(pk=self.story.pk).exists())
        self.client.post(reverse("prep:story_delete", args=[self.story.pk]))
        self.assertFalse(Story.objects.filter(pk=self.story.pk).exists())

    def test_dashboard_flags_gaps(self):
        Question.objects.create(owner=self.user, text="Tell me about a failure.")
        r = self.client.get(reverse("prep:dashboard"))
        self.assertContains(r, "Tell me about a failure.")


class PracticeTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.q = Question.objects.create(owner=self.user, text="Due one", due_at=timezone.now() - timedelta(hours=1))

    def test_shows_due_question(self):
        r = self.client.get(reverse("prep:practice"))
        self.assertContains(r, "Due one")

    def test_rating_saves_attempt_and_reschedules(self):
        r = self.client.post(reverse("prep:practice_rate", args=[self.q.pk]), {
            "rating": 3, "duration_seconds": 95, "answer_text": "I did X", "notes": "ok", "ai_feedback": "", "mode": "due",
        })
        self.assertEqual(r.status_code, 302)
        attempt = PracticeAttempt.objects.get()
        self.assertEqual((attempt.rating, attempt.duration_seconds), (3, 95))
        self.q.refresh_from_db()
        self.assertGreater(self.q.due_at, timezone.now())
        self.assertEqual(self.q.repetitions, 1)

    def test_missing_rating_does_not_save(self):
        self.client.post(reverse("prep:practice_rate", args=[self.q.pk]), {"notes": "x"})
        self.assertFalse(PracticeAttempt.objects.exists())

    def test_caught_up_message(self):
        self.q.due_at = timezone.now() + timedelta(days=2)
        self.q.save()
        r = self.client.get(reverse("prep:practice"))
        self.assertContains(r, "All caught up")

    def test_random_mode_ignores_due_date(self):
        self.q.due_at = timezone.now() + timedelta(days=2)
        self.q.save()
        r = self.client.get(reverse("prep:practice"), {"mode": "random"})
        self.assertContains(r, "Due one")

    @override_settings(ANTHROPIC_API_KEY="")
    def test_ai_feedback_off_without_key(self):
        r = self.client.post(reverse("prep:practice_feedback", args=[self.q.pk]), {"answer": "hi"})
        self.assertEqual(r.status_code, 400)
        self.assertNotContains(self.client.get(reverse("prep:practice")), "Get AI feedback")

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_ai_feedback_success(self):
        with mock.patch("prep.ai.get_feedback", return_value="Nice STAR."):
            r = self.client.post(reverse("prep:practice_feedback", args=[self.q.pk]), {"answer": "hi"})
        self.assertEqual(r.json(), {"feedback": "Nice STAR."})

    def test_streak(self):
        today = timezone.localdate()
        for days_ago in (0, 1, 2, 4):
            a = PracticeAttempt.objects.create(question=self.q, rating=3)
            PracticeAttempt.objects.filter(pk=a.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        self.assertEqual(practice_streak(self.user, today), 3)


class SeedCommandTests(LoggedInTestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_questions", stdout=mock.MagicMock())
        n = Question.objects.count()
        self.assertGreater(n, 20)
        call_command("seed_questions", stdout=mock.MagicMock())
        self.assertEqual(Question.objects.count(), n)


class ParserTests(LoggedInTestCase):
    PASTE = """Interview notes - Shopify, Oct 2026

1. Tell me about yourself.
2) Tell me about a time you had to deal with a difficult customer and
how you resolved it.
- What’s the difference between a process and a thread?
Q4: How would you design a rate limiter?
3. tell me about yourself
"""

    def test_cleans_bullets_numbers_and_joins_wrapped_lines(self):
        qs = importing.parse_questions(self.PASTE)
        self.assertEqual(qs, [
            "Interview notes - Shopify, Oct 2026",
            "Tell me about yourself.",
            "Tell me about a time you had to deal with a difficult customer and how you resolved it.",
            "What's the difference between a process and a thread?",
            "How would you design a rate limiter?",
        ])

    def test_guess_category(self):
        self.assertEqual(importing.guess_category("Tell me about yourself"), Question.GENERAL)
        self.assertEqual(importing.guess_category("Describe a time you failed."), Question.BEHAVIORAL)
        self.assertEqual(importing.guess_category("Explain how a hash map works"), Question.TECHNICAL)

    def test_heading_is_not_a_question(self):
        self.assertFalse(importing.looks_like_question("Interview notes - Shopify, Oct 2026"))
        self.assertTrue(importing.looks_like_question("Walk me through your resume"))

    def test_normalize_ignores_case_and_punctuation(self):
        self.assertEqual(importing.normalize("Tell me about YOURSELF?"), importing.normalize("tell me about yourself."))


class ImportTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("prep:question_import")
        self.existing = Question.objects.create(owner=self.user, text="Why do you want to work here?", category=Question.GENERAL)

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_preview_saves_nothing_and_flags_existing(self):
        r = self.client.post(self.url, {"text": "1. why do you want to work here\n2. What is a REST API?", "action": "preview", "source": "interview"})
        self.assertContains(r, "seen before")
        self.assertContains(r, "What is a REST API?")
        self.assertEqual(Question.objects.count(), 1)

    def test_import_creates_new_and_logs_repeat(self):
        r = self.client.post(self.url, {
            "text": "ignored on import", "action": "import",
            "source": "interview", "company": "Shopify", "seen_on": "2026-10-20", "tags_text": "shopify",
            "row_text": ["why do you want to work here", "What is a REST API?", "Skip me please?"],
            "row_category": ["general", "technical", "general"],
            "row_include": ["0", "1"],
        })
        self.assertRedirects(r, reverse("prep:question_list") + "?sort=recent")
        self.assertEqual(Question.objects.count(), 2)
        api = Question.objects.get(text="What is a REST API?")
        self.assertEqual(api.category, Question.TECHNICAL)
        self.assertEqual([t.name for t in api.tags.all()], ["shopify"])
        self.assertEqual(self.existing.sightings.get().company, "Shopify")
        self.assertEqual(api.sightings.get().seen_on.isoformat(), "2026-10-20")

    def test_import_without_source_logs_no_sightings(self):
        self.client.post(self.url, {
            "text": "x", "action": "import", "source": "",
            "row_text": ["What is a REST API?"], "row_category": ["technical"], "row_include": ["0"],
        })
        self.assertTrue(Question.objects.filter(text="What is a REST API?").exists())
        self.assertFalse(QuestionSighting.objects.exists())

    def test_nothing_selected(self):
        r = self.client.post(self.url, {"text": "x", "action": "import", "row_text": ["What is a REST API?"], "row_category": ["technical"]})
        self.assertContains(r, "Nothing was selected")
        self.assertEqual(Question.objects.count(), 1)

    def test_empty_paste(self):
        r = self.client.post(self.url, {"text": "\n  - \n", "action": "preview"})
        self.assertContains(r, "Couldn")


class SightingTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.q = Question.objects.create(owner=self.user, text="Tell me about a time you failed.")

    def test_create_form_logs_sighting(self):
        self.client.post(reverse("prep:question_create"), {
            "text": "Describe a conflict.", "category": "behavioral", "source": "application", "company": "Catalis",
        })
        s = QuestionSighting.objects.get()
        self.assertEqual((s.source, s.company, s.question.text), ("application", "Catalis", "Describe a conflict."))

    def test_add_and_remove_sighting(self):
        self.client.post(reverse("prep:question_add_sighting", args=[self.q.pk]), {"source": "interview", "company": "Acme"})
        s = self.q.sightings.get()
        self.assertContains(self.client.get(self.q.get_absolute_url()), "Acme")
        self.client.post(reverse("prep:sighting_delete", args=[s.pk]))
        self.assertFalse(self.q.sightings.exists())

    def test_list_filters_and_company_search(self):
        other = Question.objects.create(owner=self.user, text="What is a hash map?")
        QuestionSighting.objects.create(question=self.q, source="interview", company="Shopify")
        QuestionSighting.objects.create(question=self.q, source="interview", company="shopify")
        r = self.client.get(reverse("prep:question_list"), {"seen": "interview"})
        self.assertContains(r, self.q.text)
        self.assertNotContains(r, other.text)
        self.assertContains(r, "Seen 2×")
        r = self.client.get(reverse("prep:question_list"), {"q": "shopify"})
        self.assertContains(r, self.q.text)
        r = self.client.get(reverse("prep:question_list"), {"seen": "unseen", "sort": "seen"})
        self.assertContains(r, other.text)
        self.assertNotContains(r, self.q.text)

    def test_companies_deduped_case_insensitively(self):
        QuestionSighting.objects.create(question=self.q, company="Shopify")
        QuestionSighting.objects.create(question=self.q, company="SHOPIFY")
        QuestionSighting.objects.create(question=self.q, company="Catalis")
        self.assertEqual(self.q.companies, ["Shopify", "Catalis"])

    def test_practice_only_seen_questions(self):
        Question.objects.create(owner=self.user, text="Never seen question?")
        QuestionSighting.objects.create(question=self.q, source="interview")
        for _ in range(5):
            r = self.client.get(reverse("prep:practice"), {"mode": "random", "seen": "any"})
            self.assertContains(r, self.q.text)

    def test_dashboard_most_seen(self):
        QuestionSighting.objects.create(question=self.q, company="Acme")
        self.assertContains(self.client.get(reverse("prep:dashboard")), "Questions you keep seeing")


class StoryForQuestionTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.q = Question.objects.create(owner=self.user, text="Tell me about a time you failed.", notes="Use the capstone outage")
        self.other = Question.objects.create(owner=self.user, text="Describe a conflict with a teammate.")

    def test_question_pinned_at_top_of_new_story(self):
        r = self.client.get(reverse("prep:story_create"), {"question": self.q.pk})
        self.assertContains(r, 'class="attached-text">Tell me about a time you failed.')
        self.assertContains(r, f'name="questions" value="{self.q.pk}" checked')
        self.assertContains(r, "Use the capstone outage")
        self.assertContains(r, self.q.get_absolute_url())  # back link goes to the question

    def test_bad_question_param_is_ignored(self):
        for value in ("abc", "99999"):
            r = self.client.get(reverse("prep:story_create"), {"question": value})
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'id="no-question"')

    def test_save_links_question_and_keeps_brainstorm(self):
        self.client.post(reverse("prep:story_create"), {
            "title": "Capstone outage", "brainstorm": "db migration broke prod, 3 hrs",
            "questions": ["", str(self.q.pk)],
        })
        story = Story.objects.get(title="Capstone outage")
        self.assertEqual(story.brainstorm, "db migration broke prod, 3 hrs")
        self.assertEqual(list(story.questions.all()), [self.q])
        self.assertContains(self.client.get(story.get_absolute_url()), "db migration broke prod")

    def test_attach_several_and_unlink_on_edit(self):
        story = Story.objects.create(owner=self.user, title="S")
        story.questions.add(self.q)
        r = self.client.get(reverse("prep:story_update", args=[story.pk]))
        self.assertContains(r, f'name="questions" value="{self.q.pk}" checked')
        self.client.post(reverse("prep:story_update", args=[story.pk]), {"title": "S", "questions": [str(self.other.pk)]})
        self.assertEqual(list(story.questions.all()), [self.other])

    def test_failed_submit_keeps_attached_question(self):
        r = self.client.post(reverse("prep:story_create"), {"title": "", "questions": [str(self.q.pk)]})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="attached-text">Tell me about a time you failed.')
        self.assertFalse(Story.objects.exists())

    def test_brainstorm_is_searchable(self):
        Story.objects.create(owner=self.user, title="Hidden", brainstorm="kubernetes rollback")
        self.assertContains(self.client.get(reverse("prep:story_list"), {"q": "kubernetes"}), "Hidden")


class OldProjectUrlsTests(LoggedInTestCase):
    def test_old_prep_project_urls_redirect_to_journal(self):
        p = Project.objects.create(owner=self.user, name="X")
        r = self.client.get(reverse("prep:project_detail", args=[p.pk]))
        self.assertRedirects(r, reverse("journal:project_detail", args=[p.pk]), status_code=301)
