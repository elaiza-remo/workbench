"""GitHub-style contributions graph of everything you do in Workbench.

One square per day for the last year. A day's count is commits + journal notes
+ practice runs + new stories, and the shade (levels 0–4) is relative to your
own busiest days, the same way GitHub does it.
"""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

KINDS = [
    ("commits", "commit", "commits"),
    ("notes", "note", "notes"),
    ("practice", "practice run", "practice runs"),
    ("stories", "story", "stories"),
]
WEEKS = 53


def _local_dates(values):
    for dt in values:
        yield timezone.localtime(dt).date()


def _counts(user, start):
    from journal.models import Commit, Note
    from prep.models import PracticeAttempt, Story

    start_dt = timezone.make_aware(
        timezone.datetime.combine(start, timezone.datetime.min.time()), timezone.get_current_timezone()
    )
    per_day = defaultdict(lambda: defaultdict(int))
    sources = {
        "commits": _local_dates(
            Commit.objects.for_user(user).filter(committed_at__gte=start_dt).values_list("committed_at", flat=True)
        ),
        "notes": Note.objects.for_user(user).filter(happened_on__gte=start).values_list("happened_on", flat=True),
        "practice": _local_dates(
            PracticeAttempt.objects.for_user(user).filter(created_at__gte=start_dt).values_list("created_at", flat=True)
        ),
        "stories": _local_dates(
            Story.objects.for_user(user).filter(created_at__gte=start_dt).values_list("created_at", flat=True)
        ),
    }
    for kind, days in sources.items():
        for day in days:
            per_day[day][kind] += 1
    return per_day


def _thresholds(totals):
    """Cut-offs for levels 1–4, from the spread of your non-zero days."""
    nonzero = sorted(t for t in totals if t > 0)
    if not nonzero:
        return (1, 2, 3)
    def pct(p):
        return nonzero[min(len(nonzero) - 1, int(p * (len(nonzero) - 1)))]
    return (pct(0.25), pct(0.5), pct(0.75))


def _level(total, cuts):
    if total <= 0:
        return 0
    if total <= cuts[0]:
        return 1
    if total <= cuts[1]:
        return 2
    if total <= cuts[2]:
        return 3
    return 4


def _describe(day, counts):
    parts = []
    for key, one, many in KINDS:
        n = counts.get(key, 0)
        if n:
            parts.append(f"{n} {one if n == 1 else many}")
    when = f"{day:%A}, {day:%b} {day.day}, {day.year}"
    return f"{', '.join(parts)} on {when}" if parts else f"No activity on {when}"


def _streaks(per_day, start, today):
    current = longest = run = 0
    day = start
    while day <= today:
        run = run + 1 if sum(per_day.get(day, {}).values()) else 0
        longest = max(longest, run)
        day += timedelta(days=1)
    # Current streak: ending today, or yesterday if today is still empty.
    day = today if sum(per_day.get(today, {}).values()) else today - timedelta(days=1)
    while day >= start and sum(per_day.get(day, {}).values()):
        current += 1
        day -= timedelta(days=1)
    return current, longest


def build(user, today=None, weeks=WEEKS):
    today = today or timezone.localdate()
    days_since_sunday = (today.weekday() + 1) % 7
    start = today - timedelta(days=days_since_sunday + (weeks - 1) * 7)
    per_day = _counts(user, start)

    totals = [sum(per_day.get(start + timedelta(days=i), {}).values()) for i in range((today - start).days + 1)]
    cuts = _thresholds(totals)

    columns, months = [], []
    last_month_col = -3
    for w in range(weeks):
        week_start = start + timedelta(days=w * 7)
        cells = []
        for d in range(7):
            day = week_start + timedelta(days=d)
            if day > today:
                cells.append(None)
                continue
            counts = per_day.get(day, {})
            total = sum(counts.values())
            cells.append({
                "date": day.isoformat(),
                "total": total,
                "level": _level(total, cuts),
                "label": _describe(day, counts),
            })
        columns.append(cells)
        first_of_month = next((week_start + timedelta(days=d) for d in range(7)
                               if (week_start + timedelta(days=d)).day == 1), None)
        if (w == 0 and week_start.day <= 21) or first_of_month:
            label_day = first_of_month or week_start
            if w - last_month_col >= 3:
                months.append({"col": w, "label": f"{label_day:%b}"})
                last_month_col = w

    by_kind = defaultdict(int)
    for counts in per_day.values():
        for key, n in counts.items():
            by_kind[key] += n
    current, longest = _streaks(per_day, start, today)
    return {
        "columns": columns,
        "months": months,
        "weeks": weeks,
        "total": sum(totals),
        "active_days": sum(1 for t in totals if t),
        "current_streak": current,
        "longest_streak": longest,
        "breakdown": [
            {"key": key, "label": many, "count": by_kind.get(key, 0)} for key, _one, many in KINDS
        ],
    }
