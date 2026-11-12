"""Turn a pasted block of text into clean interview questions.

Handles the usual messes from copying out of job postings, notes apps and
emails: bullets, numbering, "Q3:" prefixes, smart quotes, and questions that
wrapped onto a second line.
"""
import re

from .models import Question, QuestionSighting, Tag

MAX_LEN = 500
MIN_LEN = 8

_PREFIX = re.compile(
    r"""^\s*(?:
        [-*•◦▪‣–—·>]+                       # bullets
      | \(?\d{1,3}\s*[.)\]:-]               # 1.  1)  (1)  1:  1-
      | \(?[a-hA-H][.)]\s                    # a)  b.
      | Q(?:uestion)?\s*\#?\d*\s*[:.)-]     # Q:  Q1:  Question 3.
    )\s*""",
    re.VERBOSE,
)
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_TERMINAL = ("?", ".", "!", ":", ")")


def _clean(line):
    line = line.translate(_QUOTES).strip()
    for _ in range(2):  # e.g. "- 1. Tell me…"
        line = _PREFIX.sub("", line, count=1)
    line = line.strip().strip('"').strip()
    return re.sub(r"\s+", " ", line)


def normalize(text):
    """Comparison key: case, spacing, quotes and end punctuation don't matter."""
    text = text.translate(_QUOTES).lower()
    text = re.sub(r"[\"']", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(" ?.!:")


def parse_questions(text):
    """Split pasted text into a de-duplicated list of question strings."""
    questions = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        starts_new_item = bool(_PREFIX.match(raw))
        line = _clean(raw)
        if not line:
            continue
        # A line that wrapped: previous line had no end punctuation and this one
        # starts lowercase without its own bullet/number.
        if (
            questions
            and not starts_new_item
            and not questions[-1].endswith(_TERMINAL)
            and line[0].islower()
        ):
            questions[-1] = f"{questions[-1]} {line}"
            continue
        questions.append(line)

    seen, result = set(), []
    for q in questions:
        key = normalize(q)
        if len(key) < MIN_LEN or not re.search(r"[a-zA-Z]", key) or key in seen:
            continue
        seen.add(key)
        result.append(q[:MAX_LEN])
    return result


_GENERAL = re.compile(
    r"tell (me|us) about yourself|describe yourself|walk (me|us) through your (resume|background)"
    r"|why do you want|why are you interested|why (should we|would we) hire|what interests you"
    r"|where do you see yourself|strengths?\b|weakness|salary|compensation|notice period"
    r"|questions for (me|us)|why (this|our) (company|team|role)|availability|work authori[sz]ation"
    r"|how did you hear",
    re.I,
)
_BEHAVIORAL = re.compile(
    r"tell (me|us) about (a|an|the) (time|situation|project|occasion)|describe (a|an) (time|situation|occasion)"
    r"|give (me |us )?an example|a time (when|you|that)|how (did|have) you (handle|dealt|deal|manage|approach)"
    r"|what did you learn|walk (me|us) through a (time|situation)|biggest (mistake|failure|challenge|accomplishment)"
    r"|proudest|proud of|conflict|disagree|difficult (person|teammate|coworker|co-worker|customer|manager|stakeholder)"
    r"|most (challenging|difficult)|have you ever",
    re.I,
)
_TECHNICAL = re.compile(
    r"\b(explain|difference between|what is (a|an|the)|how does|how would you (design|implement|build|scale|optimi[sz]e)"
    r"|design (a|an)|implement|write (a|an) (function|program|query|class)|complexity|big[- ]?o|algorithm"
    r"|data structure|sql|database|api|rest(ful)?|http|tcp|dns|thread|process|linked list|array|hash|binary"
    r"|tree|graph|recursion|git|docker|kubernetes|class(es)?|object[- ]oriented|oop|polymorphism|inheritance"
    r"|unit test|testing|javascript|typescript|python|react|java|c\+\+|cache|caching|concurrency|memory"
    r"|index(es|ing)?|scal(e|ing|ability)|latency|debug(ging)?)\b",
    re.I,
)


def guess_category(text):
    if _GENERAL.search(text):
        return Question.GENERAL
    if _BEHAVIORAL.search(text):
        return Question.BEHAVIORAL
    if _TECHNICAL.search(text):
        return Question.TECHNICAL
    return Question.GENERAL


_QUESTION_START = re.compile(
    r"^(tell|describe|explain|give|walk|talk|share|how|what|what's|why|when|where|who|which|can|could|would|"
    r"should|have|has|do|does|did|are|is|were|was|will|implement|design|write|compare|define|list|name|"
    r"if|imagine|suppose|in your|outline|discuss)\b",
    re.I,
)


def looks_like_question(text):
    """False for stray headings like 'Interview notes – Oct 2026'."""
    return text.rstrip().endswith("?") or bool(_QUESTION_START.match(text.strip()))


def existing_by_key(user):
    return {normalize(q.text): q for q in Question.objects.for_user(user)}


def build_preview(user, texts, category=""):
    """Rows for the preview table: text, category, and any matching question."""
    existing = existing_by_key(user)
    return [
        {
            "text": t,
            "category": category or guess_category(t),
            "existing": existing.get(normalize(t)),
            "likely": looks_like_question(t),
        }
        for t in texts
    ]


def import_rows(user, rows, source="", company="", seen_on=None, tag_names=()):
    """Create new questions and log sightings of ones already in the library.

    `rows` is a list of (text, category) pairs. Returns (created, repeats).
    """
    existing = existing_by_key(user)
    tags = [Tag.objects.get_or_create(owner=user, name=n)[0] for n in tag_names]
    valid_categories = dict(Question.CATEGORY_CHOICES)
    created, repeats = [], []

    for text, category in rows:
        text = _clean(text)[:MAX_LEN]
        key = normalize(text)
        if len(key) < MIN_LEN:
            continue
        question = existing.get(key)
        if question is None:
            question = Question.objects.create(
                owner=user,
                text=text,
                category=category if category in valid_categories else guess_category(text),
            )
            existing[key] = question
            created.append(question)
        elif question not in repeats and question not in created:
            repeats.append(question)
        else:
            continue  # same question twice in one paste
        if tags:
            question.tags.add(*tags)
        if source:
            QuestionSighting.objects.create(
                question=question, source=source, company=company.strip(), seen_on=seen_on
            )
    return created, repeats
