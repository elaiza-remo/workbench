from django.contrib.auth import get_user_model
from django.test import TestCase


class LoggedInTestCase(TestCase):
    """A TestCase whose client is signed in as `self.user` (a superuser, like you)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("elaiza", "elaiza@example.com", "a-strong-password-123")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
