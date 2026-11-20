import base64
import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.management.commands.create_testing_party import EVALUATORS

HOST = "pawpal-integration.us-east-2.elasticbeanstalk.com"
COMMAND = "apply_testing_party_passwords"


class ApplyTestingPartyPasswordsTests(TestCase):
    def setUp(self):
        self.credentials = {
            f"{prefix}_{suffix}": f"test-password-{prefix}-{suffix}"
            for prefix, *_ in EVALUATORS
            for suffix in ("owner", "caregiver")
        }

    def encoded(self, credentials):
        return base64.b64encode(json.dumps(credentials).encode("utf-8")).decode("ascii")

    def run_command(self, credentials=None, enabled="yes"):
        payload = self.encoded(self.credentials if credentials is None else credentials)
        with patch.dict(
            "os.environ",
            {
                "TESTING_PARTY_APPLY": enabled,
                "TESTING_PARTY_CREDENTIALS_B64": payload,
            },
        ):
            return call_command(COMMAND, stdout=StringIO())

    @override_settings(DEBUG=True, ALLOWED_HOSTS=[HOST])
    def test_rejects_debug_mode(self):
        with self.assertRaises(CommandError):
            self.run_command()

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["localhost"])
    def test_rejects_wrong_host(self):
        with self.assertRaises(CommandError):
            self.run_command()

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_requires_explicit_enable_flag(self):
        with self.assertRaises(CommandError):
            self.run_command(enabled="no")

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_rejects_missing_credentials(self):
        with patch.dict(
            "os.environ",
            {
                "TESTING_PARTY_APPLY": "yes",
                "TESTING_PARTY_CREDENTIALS_B64": "",
            },
        ):
            with self.assertRaises(CommandError):
                call_command(COMMAND)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_rejects_invalid_base64(self):
        with patch.dict(
            "os.environ",
            {
                "TESTING_PARTY_APPLY": "yes",
                "TESTING_PARTY_CREDENTIALS_B64": "!!!",
            },
        ):
            with self.assertRaises(CommandError):
                call_command(COMMAND)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_rejects_wrong_account_set(self):
        with self.assertRaises(CommandError):
            self.run_command(credentials={"wrong_user": "password"})

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_rejects_empty_password(self):
        credentials = self.credentials.copy()
        first = next(iter(credentials))
        credentials[first] = ""

        with self.assertRaises(CommandError):
            self.run_command(credentials=credentials)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_rejects_missing_accounts(self):
        with self.assertRaisesMessage(CommandError, "Missing account"):
            self.run_command()

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[HOST])
    def test_updates_passwords_successfully(self):
        User = get_user_model()

        for username in self.credentials:
            User.objects.create_user(
                username=username,
                password="original-password",
            )

        self.run_command()

        for username, password in self.credentials.items():
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(password))
