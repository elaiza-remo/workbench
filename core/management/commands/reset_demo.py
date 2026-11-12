from django.core.management.base import BaseCommand

from core.demo import reset_demo


class Command(BaseCommand):
    help = "Wipe the public demo account and fill it with fresh sample data."

    def handle(self, *args, **options):
        user = reset_demo()
        self.stdout.write(self.style.SUCCESS(f"Demo account “{user.username}” reset with sample data."))
