"""Logging in is slowed down after several wrong passwords (#314)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.forms import MAX_FAILED_LOGINS
from accounts.models import AccountProfile

LOGIN = reverse("login")


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            "team1_owner", password="right-pass-123"
        )
        AccountProfile.objects.create(user=self.user)

    def attempt(self, password, username="team1_owner"):
        return self.client.post(LOGIN, {"username": username, "password": password})

    def test_locked_after_too_many_wrong_passwords(self):
        for _ in range(MAX_FAILED_LOGINS):
            response = self.attempt("wrong")
            self.assertNotContains(response, "Too many failed attempts")
        response = self.attempt("wrong")
        self.assertContains(response, "Too many failed attempts")
        # Even the right password waits until the lockout ends.
        response = self.attempt("right-pass-123")
        self.assertContains(response, "Too many failed attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_other_usernames_are_not_locked(self):
        for _ in range(MAX_FAILED_LOGINS):
            self.attempt("wrong", username="someone")
        response = self.attempt("right-pass-123")
        self.assertEqual(response.status_code, 302)

    def test_success_resets_the_count(self):
        for _ in range(MAX_FAILED_LOGINS - 1):
            self.attempt("wrong")
        self.assertEqual(self.attempt("right-pass-123").status_code, 302)
        self.client.logout()
        for _ in range(MAX_FAILED_LOGINS - 1):
            self.attempt("wrong")
        self.assertEqual(self.attempt("right-pass-123").status_code, 302)
