import csv
import io
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.management.commands.create_testing_party import (
    EVALUATORS,
    INTEGRATION_HOST,
    generate_password,
    load_demo_passwords,
)
from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from pets.models import Pet

User = get_user_model()


@override_settings(DEBUG=True)
class CreateTestingPartyTests(TestCase):
    def run_command(self, *args, **kwargs):
        output = io.StringIO()
        call_command("create_testing_party", *args, stdout=output, **kwargs)
        return output.getvalue()

    def make_csv(self, directory, passwords=None):
        path = Path(directory) / "credentials.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["username", "password"])

            for prefix, *_ in EVALUATORS:
                for suffix in ("owner", "caregiver"):
                    username = f"{prefix}_{suffix}"
                    password = (
                        passwords[username]
                        if passwords is not None
                        else f"TestPassword!{username}"
                    )
                    writer.writerow([username, password])

        return path

    def test_creates_all_demo_accounts_and_sample_data(self):
        self.run_command()

        self.assertEqual(User.objects.filter(username__startswith="prof_").count(), 2)

        for prefix, *_ in EVALUATORS:
            owner = User.objects.get(username=f"{prefix}_owner")
            caregiver = User.objects.get(username=f"{prefix}_caregiver")

            self.assertEqual(
                AccountProfile.objects.get(user=owner).role,
                AccountProfile.Role.PET_OWNER,
            )
            self.assertEqual(
                AccountProfile.objects.get(user=caregiver).role,
                AccountProfile.Role.CAREGIVER,
            )

            self.assertTrue(CaregiverProfile.objects.filter(user=caregiver).exists())
            self.assertTrue(Pet.objects.filter(owner=owner).exists())

        self.assertEqual(
            User.objects.filter(
                username__in=[
                    f"{prefix}_{suffix}"
                    for prefix, *_ in EVALUATORS
                    for suffix in ("owner", "caregiver")
                ]
            ).count(),
            14,
        )

    def test_running_twice_does_not_create_duplicates(self):
        self.run_command()
        self.run_command()

        self.assertEqual(User.objects.count(), 14)
        self.assertEqual(CaregiverProfile.objects.count(), 7)
        self.assertEqual(Pet.objects.count(), 7)

    def test_dry_run_does_not_modify_database(self):
        output = self.run_command(dry_run=True)

        self.assertIn("DRY RUN", output)
        self.assertIn("PLAN:", output)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Pet.objects.count(), 0)

    def test_csv_passwords_are_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_csv(directory)

            self.run_command(credentials_file=path)

            for prefix, *_ in EVALUATORS:
                for suffix in ("owner", "caregiver"):
                    username = f"{prefix}_{suffix}"
                    user = User.objects.get(username=username)
                    self.assertTrue(user.check_password(f"TestPassword!{username}"))

    def test_existing_passwords_are_updated_from_csv(self):
        self.run_command()

        with tempfile.TemporaryDirectory() as directory:
            path = self.make_csv(directory)
            self.run_command(credentials_file=path)

            user = User.objects.get(username="prof_owner")
            self.assertTrue(user.check_password("TestPassword!prof_owner"))

    def test_missing_csv_is_rejected(self):
        with self.assertRaisesMessage(CommandError, "Credentials file not found"):
            load_demo_passwords(Path("nonexistent_credentials_file.csv"))

    def test_duplicate_csv_username_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_csv(directory)

            with path.open("a", encoding="utf-8") as file:
                file.write("\nprof_owner,DuplicatePassword")

            with self.assertRaisesMessage(CommandError, "Duplicate username"):
                load_demo_passwords(path)

    def test_csv_missing_required_columns_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("name,secret\nalice,hello\n", encoding="utf-8")

            with self.assertRaisesMessage(CommandError, "username,password columns"):
                load_demo_passwords(path)

    def test_csv_missing_accounts_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incomplete.csv"
            path.write_text(
                "username,password\nprof_owner,TestPassword!",
                encoding="utf-8",
            )

            with self.assertRaisesMessage(CommandError, "exactly the 14 expected"):
                load_demo_passwords(path)

    def test_empty_csv_password_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty_password.csv"
            path.write_text(
                "username,password\nprof_owner,\n",
                encoding="utf-8",
            )

            with self.assertRaisesMessage(CommandError, "Empty password"):
                load_demo_passwords(path)

    def test_wrong_existing_role_is_rejected(self):
        self.run_command()

        profile = AccountProfile.objects.get(user__username="prof_owner")
        profile.role = AccountProfile.Role.CAREGIVER
        profile.save()

        with self.assertRaisesMessage(CommandError, "missing or incorrect role"):
            self.run_command()

    @override_settings(DEBUG=False)
    def test_production_requires_explicit_permission(self):
        with self.assertRaisesMessage(CommandError, "requires --allow-production"):
            self.run_command()

    @override_settings(DEBUG=False)
    def test_non_integration_environment_is_rejected(self):
        with mock.patch.dict(
            os.environ,
            {"DJANGO_ALLOWED_HOSTS": "pawpal-env.example.com"},
        ):
            with self.assertRaisesMessage(CommandError, "non-integration environment"):
                self.run_command(allow_production=True)

    @override_settings(DEBUG=False)
    def test_integration_requires_credentials_file(self):
        with mock.patch.dict(
            os.environ,
            {"DJANGO_ALLOWED_HOSTS": INTEGRATION_HOST},
        ):
            with self.assertRaisesMessage(CommandError, "requires --credentials-file"):
                self.run_command(allow_production=True)

    def test_generated_password_length(self):
        password = generate_password()

        self.assertEqual(len(password), 20)
        self.assertTrue(any(char.isdigit() for char in password))
