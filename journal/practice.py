"""Turn a project and its journal notes into interview practice questions.

Interviewers dig into the projects on your resume: why you built it that way,
what broke, how you used AI. These questions rehearse exactly that, and when
you practise one, the note it came from is there to check your answer against.
"""
from prep.importing import normalize
from prep.models import Question

from .models import Note


def _quote(title):
    return "“" + title.strip().rstrip(".!?") + "”"


def _note_question(note):
    p, t = note.project.name, _quote(note.title)
    if note.kind == Note.DECISION:
        return f"On {p}, you decided {t}. Why, and what alternatives did you consider?"
    if note.kind == Note.ISSUE:
        return f"Tell me about {t} on {p}. How did you figure out what was wrong, and how did you fix it?"
    if note.kind == Note.AI:
        tool = note.ai_tool.strip() or "AI"
        return f"On {p}, you used {tool} for {t}. How did you check what it gave you, and what did you change?"
    if note.kind == Note.LEARNING:
        return f"What did you learn from {t} on {p}, and how has it changed the way you work?"
    return f"Tell me about {t} on {p}."


def _project_questions(project):
    p = project.name
    questions = [
        (f"Walk me through {p}. What does it do, who is it for, and what was your role?", "Overview"),
        (f"What was the hardest part of building {p}?", "Overview"),
        (f"If you rebuilt {p} today, what would you do differently?", "Overview"),
    ]
    if project.tech_stack.strip():
        questions.append((f"Why did you choose {project.tech_stack.strip()} for {p}?", "Tech stack"))
    if project.notes.filter(kind=Note.AI).exists():
        questions.append((f"How did you use AI tools while building {p}, and how did you make sure the output was right?", "AI usage"))
    return questions


def suggest_questions(project, note=None):
    """Proposed questions as dicts: text, note, reason, existing (a matching Question or None).

    With `note`, only that note's question. Plain "Note" entries are left out of
    the project-wide list because they're usually too loose to make good questions.
    """
    rows = []
    if note is None:
        rows += [{"text": text, "note": None, "reason": reason} for text, reason in _project_questions(project)]
        notes = project.notes.exclude(kind=Note.NOTE)
    else:
        notes = [note]
    for n in notes:
        rows.append({"text": _note_question(n), "note": n, "reason": n.get_kind_display()})

    mine = Question.objects.for_user(project.owner)
    existing_text = {normalize(q.text): q for q in mine}
    existing_note = {q.source_note_id: q for q in mine.filter(source_note__project=project)}
    for row in rows:
        row["existing"] = existing_text.get(normalize(row["text"])) or (
            existing_note.get(row["note"].pk) if row["note"] else None
        )
    return rows


def create_questions(project, rows):
    """rows: [(text, note_or_None)]. Skips duplicates. Returns the new questions."""
    seen = {normalize(q.text) for q in Question.objects.for_user(project.owner)}
    created = []
    for text, note in rows:
        text = " ".join(text.split())[:500]
        key = normalize(text)
        if len(key) < 8 or key in seen:
            continue
        seen.add(key)
        question = Question.objects.create(
            owner=project.owner,
            text=text, category=Question.PROJECT, project=project, source_note=note,
        )
        if note is not None:
            question.stories.set(note.stories.all())
            question.tags.set(note.tags.all())
        created.append(question)
    return created
