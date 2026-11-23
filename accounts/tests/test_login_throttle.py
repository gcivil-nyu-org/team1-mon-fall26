"""Logging in is slowed down after several wrong passwords (#314)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.forms import MAX_FAILED_LOGINS, client_address
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


class ClientAddressTests(TestCase):
    def request(self, forwarded=None, remote="127.0.0.1"):
        meta = {"REMOTE_ADDR": remote}
        if forwarded is not None:
            meta["HTTP_X_FORWARDED_FOR"] = forwarded
        return type("Request", (), {"META": meta})()

    def test_behind_nginx_the_last_forwarded_address(self):
        # A made-up first entry is ignored: nginx adds the real one last.
        self.assertEqual(
            client_address(self.request("6.6.6.6, 203.0.113.7")), "203.0.113.7"
        )

    @override_settings(TRUSTED_PROXIES=2)
    def test_behind_a_load_balancer_too(self):
        self.assertEqual(
            client_address(self.request("203.0.113.7, 172.31.0.5")), "203.0.113.7"
        )

    def test_without_a_proxy_header(self):
        self.assertEqual(client_address(self.request(remote="10.0.0.1")), "10.0.0.1")
        self.assertEqual(client_address(None), "")

    @override_settings(TRUSTED_PROXIES=0)
    def test_no_proxies(self):
        self.assertEqual(
            client_address(self.request("6.6.6.6", remote="10.0.0.1")), "10.0.0.1"
        )

    def test_different_visitors_have_their_own_count(self):
        user = get_user_model().objects.create_user("kat", password="right-pass-123")
        AccountProfile.objects.create(user=user)
        cache.clear()
        for _ in range(MAX_FAILED_LOGINS + 1):
            self.client.post(
                LOGIN,
                {"username": "kat", "password": "wrong"},
                HTTP_X_FORWARDED_FOR="198.51.100.1",
            )
        response = self.client.post(
            LOGIN,
            {"username": "kat", "password": "right-pass-123"},
            HTTP_X_FORWARDED_FOR="198.51.100.2",
        )
        self.assertEqual(response.status_code, 302)
