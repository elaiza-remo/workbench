"""Spaced repetition scheduling (a simplified SM-2).

After each practice attempt you rate yourself 1-4. Shaky questions come back
soon; strong ones get pushed further out each time you nail them.
"""
from datetime import timedelta

from django.utils import timezone

MIN_EASE = 1.3
RELEARN_DELAY = timedelta(minutes=10)

# Map the 1-4 rating onto SM-2's 0-5 quality scale.
_QUALITY = {2: 3, 3: 4, 4: 5}


def schedule(question, rating, now=None):
    """Update `question`'s scheduling fields in place for a 1-4 `rating`.

    Does not save; the caller decides when to write to the database.
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1, 2, 3 or 4")
    now = now or timezone.now()

    if rating == 1:  # Again: start over and see it again shortly
        question.repetitions = 0
        question.interval_days = 0
        question.ease = max(MIN_EASE, question.ease - 0.2)
        question.due_at = now + RELEARN_DELAY
        return question

    q = _QUALITY[rating]
    question.ease = max(MIN_EASE, question.ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))

    if question.repetitions == 0:
        interval = 1
    elif question.repetitions == 1:
        interval = 2 if rating == 2 else 4
    elif rating == 2:
        interval = max(question.interval_days + 1, round(question.interval_days * 1.2))
    else:
        interval = round(question.interval_days * question.ease)
        if rating == 4:
            interval = round(interval * 1.3)

    question.repetitions += 1
    question.interval_days = max(1, interval)
    question.due_at = now + timedelta(days=question.interval_days)
    return question
