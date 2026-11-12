"""Per-user data.

Every model either has an `owner` or belongs to something that does (a note
belongs to a project, a practice attempt to a question). Views always go
through `Model.objects.for_user(request.user)`, so one account can never see or
change another's data — which is what keeps the public demo account separate
from yours.
"""
from django.conf import settings
from django.db import models


class OwnedQuerySet(models.QuerySet):
    def for_user(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        lookup = getattr(self.model, "OWNER_LOOKUP", "owner")
        return self.filter(**{lookup: user})


def owner_field():
    return models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+",
    )
