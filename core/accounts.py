"""Helpers for picking which account a management command acts on."""
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError


def resolve_user(username=None):
    User = get_user_model()
    if username:
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as e:
            raise CommandError(f"No user called “{username}”.") from e
    user = User.objects.filter(is_superuser=True).order_by("pk").first()
    if user is None:
        raise CommandError("No account yet. Create one first: python manage.py createsuperuser")
    return user
