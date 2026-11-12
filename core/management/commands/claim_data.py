from django.core.management.base import BaseCommand

from core.accounts import resolve_user
from prep.models import Project, Question, Story, Tag


class Command(BaseCommand):
    help = (
        "Give all data that has no owner to an account. Run this once after upgrading, "
        "or after loading old data into a new database."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username to give the data to (default: the first superuser)")

    def handle(self, *args, user=None, **options):
        owner = resolve_user(user)
        total = 0
        for model in (Tag, Project, Story, Question):
            n = model.objects.filter(owner__isnull=True).update(owner=owner)
            total += n
            self.stdout.write(f"  {model._meta.verbose_name_plural}: {n}")
        self.stdout.write(self.style.SUCCESS(f"Gave {total} item(s) to {owner.username}."))
