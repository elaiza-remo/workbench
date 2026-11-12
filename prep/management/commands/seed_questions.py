from django.core.management.base import BaseCommand

from prep.models import Question, Tag

B, T, G = Question.BEHAVIORAL, Question.TECHNICAL, Question.GENERAL

STARTER_QUESTIONS = [
    # General / opening
    ("Tell me about yourself.", G, ["intro"]),
    ("Why do you want to work here?", G, ["motivation"]),
    ("Why are you interested in this role?", G, ["motivation"]),
    ("Where do you see yourself in a few years?", G, ["motivation", "growth"]),
    ("What questions do you have for us?", G, ["closing"]),

    # Behavioural
    ("Tell me about the most technically challenging problem you've faced.", B, ["technical challenge", "problem solving"]),
    ("Tell me about a time you dealt with a problem and solved it.", B, ["problem solving"]),
    ("Tell me about a time you disagreed with a teammate. How did you handle it?", B, ["conflict", "teamwork"]),
    ("Tell me about a time you failed or made a mistake.", B, ["failure", "growth"]),
    ("Tell me about a project you're most proud of.", B, ["ownership", "technical challenge"]),
    ("Describe a time you had to learn a new technology quickly.", B, ["learning", "growth"]),
    ("Tell me about a time you worked under a tight deadline.", B, ["deadline", "prioritisation"]),
    ("Tell me about a time you took the lead or took initiative.", B, ["leadership", "ownership"]),
    ("Tell me about a time you received critical feedback. What did you do?", B, ["feedback", "growth"]),
    ("Describe a time you had to explain something technical to a non-technical person.", B, ["communication"]),
    ("Tell me about a time you helped a frustrated customer or user.", B, ["communication", "customer focus"]),
    ("Tell me about a time you had to juggle several priorities at once.", B, ["prioritisation"]),
    ("Tell me about a time you went above and beyond.", B, ["ownership"]),
    ("Describe a time you worked with a difficult person.", B, ["conflict", "teamwork"]),
    ("Tell me about a time you debugged something hard to track down.", B, ["technical challenge", "problem solving"]),
    ("Tell me about a time you made a decision without all the information.", B, ["ambiguity", "problem solving"]),

    # Technical concepts
    ("Explain the difference between a process and a thread.", T, ["os"]),
    ("What happens when you type a URL into a browser and press Enter?", T, ["networking", "web"]),
    ("Explain Big-O notation, and the time complexity of looking something up in a hash map.", T, ["algorithms"]),
    ("What's the difference between SQL and NoSQL databases? When would you use each?", T, ["databases"]),
    ("Explain what a REST API is. What makes an API RESTful?", T, ["web", "apis"]),
    ("What is the difference between an INNER JOIN and a LEFT JOIN?", T, ["databases"]),
    ("Explain how you would design a URL shortener.", T, ["system design"]),
    ("What is a race condition, and how can you prevent one?", T, ["concurrency"]),
    ("Walk me through how you'd approach debugging a production issue.", T, ["debugging"]),
]


def seed_for(user):
    """Give `user` the starter questions they don't have yet. Returns how many were added."""
    created = 0
    for text, category, tag_names in STARTER_QUESTIONS:
        question, was_created = Question.objects.get_or_create(
            owner=user, text=text, defaults={"category": category}
        )
        if was_created:
            created += 1
            question.tags.set([Tag.objects.get_or_create(owner=user, name=n)[0] for n in tag_names])
    return created


class Command(BaseCommand):
    help = "Load a starter set of common interview questions for a user. Safe to run more than once."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username to add them for (default: the first superuser)")

    def handle(self, *args, user=None, **options):
        from core.accounts import resolve_user

        owner = resolve_user(user)
        created = seed_for(owner)
        skipped = len(STARTER_QUESTIONS) - created
        self.stdout.write(self.style.SUCCESS(
            f"Added {created} question(s) for {owner.username}; {skipped} already existed."
        ))
