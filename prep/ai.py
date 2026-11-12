"""Optional AI feedback on practice answers via the Anthropic Messages API.

Only active when ANTHROPIC_API_KEY is set. Uses the standard library so the
app has no extra dependencies.
"""
import json
import urllib.error
import urllib.request

from django.conf import settings

API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are an interview coach helping a junior software developer \
practise. Give feedback on their answer to an interview question.

For behavioural questions, check it against STAR (Situation, Task, Action, Result): \
say which parts are strong, which are thin or missing, and whether the Result is \
concrete. For technical questions, check correctness and clarity.

Be direct and specific. Keep it under 200 words, in this shape:
- What worked (1-2 bullets)
- What to fix (2-3 bullets)
- One stronger line they could use, if it helps"""


class AIFeedbackError(Exception):
    pass


def is_enabled(user=None):
    """On when an API key is set — but never for the public demo account, which anyone can use."""
    if user is not None and getattr(user, "username", None) == settings.DEMO_USERNAME:
        return False
    return bool(settings.ANTHROPIC_API_KEY)


def get_feedback(question_text, answer_text, timeout=30):
    if not is_enabled():
        raise AIFeedbackError("AI feedback is off. Set ANTHROPIC_API_KEY to turn it on.")
    if not answer_text.strip():
        raise AIFeedbackError("Write or transcribe an answer first.")

    body = json.dumps(
        {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": 600,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": f"Question: {question_text}\n\nMy answer:\n{answer_text}",
                }
            ],
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise AIFeedbackError(f"The AI service returned an error ({e.code}).") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise AIFeedbackError("Couldn't reach the AI service. Check your connection.") from e

    parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        raise AIFeedbackError("The AI service sent back an empty response.")
    return text
