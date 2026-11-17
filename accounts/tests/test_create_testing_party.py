"""create_testing_party sets up the demo accounts for the professor, the TA and
the other teams: a pet owner and a caregiver each, a caregiver profile and a
pet. It prints each new password once and never resets an existing one."""

import io
import re
import string

import json
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from accounts.management.commands.create_testing_party import (
    CAREGIVER_DATA,
    EVALUATORS,
    generate_password,
)
from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from pets.models import Pet

User = get_user_model()
USERNAMES = [
    f"{prefix}_{suffix}"
    for prefix, *_ in EVALUATORS
    for suffix in ("owner", "caregiver")
]


def run(*args):
    out = io.StringIO()
    call_command("create_testing_party", *args, stdout=out)
    return out.getvalue()


def printed_passwords(output):
    """{username: password} from the credentials block."""
    block = output.split("NEW ACCOUNT CREDENTIALS")[-1]
    return dict(re.findall(r"^(\w+_(?:owner|caregiver)): (\S+)$", block, re.M))


class GeneratePasswordTests(TestCase):
    def test_random_passwords_of_the_given_length(self):
        alphabet = set(string.ascii_letters + string.digits + "!@#$%")
        first, second = generate_password(), generate_password(12)
        self.assertEqual(len(first), 20)
        self.assertEqual(len(second), 12)
        self.assertLessEqual(set(first), alphabet)
        self.assertNotEqual(first, generate_password())


class CreateTestingPartyTests(TestCase):
    def test_blocked_on_production_without_the_flag(self):
        # The test runner runs with DEBUG=False, like the servers.
        with self.assertRaisesMessage(CommandError, "Production changes are blocked"):
            run()
        self.assertFalse(User.objects.filter(username__in=USERNAMES).exists())

    def test_dry_run_only_prints_the_plan(self):
        output = run("--dry-run")
        self.assertIn("PLAN: prof_owner", output)
        self.assertIn("PLAN: ta_caregiver", output)
        self.assertIn("PLAN: Caregiver profile for Sophie Bennett", output)
        self.assertIn("PLAN: Mochi (Cat)", output)
        self.assertIn("DRY RUN", output)
        self.assertFalse(User.objects.filter(username__in=USERNAMES).exists())
        self.assertFalse(CaregiverProfile.objects.exists())

    def test_creates_every_account_profile_and_pet(self):
        output = run("--allow-production")
        self.assertIn("Setup completed successfully.", output)
        for prefix, label, pet_name, pet_type in EVALUATORS:
            owner = User.objects.get(username=f"{prefix}_owner")
            caregiver = User.objects.get(username=f"{prefix}_caregiver")
            self.assertEqual(owner.account_profile.role, AccountProfile.Role.PET_OWNER)
            self.assertEqual(
                caregiver.account_profile.role, AccountProfile.Role.CAREGIVER
            )
            # Demo accounts can log in straight away.
            self.assertTrue(owner.account_profile.email_verified)
            self.assertTrue(caregiver.account_profile.email_verified)
            profile = CaregiverProfile.objects.get(user=caregiver)
            self.assertEqual((profile.name, profile.bio), CAREGIVER_DATA[prefix])
            pet = Pet.objects.get(owner=owner)
            self.assertEqual((pet.name, pet.pet_type.name), (pet_name, pet_type))
        self.assertEqual(User.objects.filter(username__in=USERNAMES).count(), 14)

    def test_printed_passwords_log_in(self):
        passwords = printed_passwords(run("--allow-production"))
        self.assertEqual(sorted(passwords), sorted(USERNAMES))
        self.assertTrue(
            self.client.login(username="prof_owner", password=passwords["prof_owner"])
        )
        self.assertTrue(
            self.client.login(
                username="team5_caregiver", password=passwords["team5_caregiver"]
            )
        )

    @override_settings(DEBUG=True)
    def test_runs_locally_without_the_flag(self):
        run()
        self.assertEqual(User.objects.filter(username__in=USERNAMES).count(), 14)

    def test_running_again_keeps_accounts_and_passwords(self):
        first = printed_passwords(run("--allow-production"))
        output = run("--allow-production")
        self.assertIn("EXISTS: prof_owner", output)
        self.assertIn("EXISTS CAREGIVER PROFILE: Sophie Bennett", output)
        self.assertIn("EXISTS PET: Mochi", output)
        self.assertNotIn("NEW ACCOUNT CREDENTIALS", output)
        self.assertEqual(User.objects.filter(username__in=USERNAMES).count(), 14)
        self.assertEqual(CaregiverProfile.objects.count(), 7)
        self.assertEqual(Pet.objects.filter(owner__username__in=USERNAMES).count(), 7)
        # The first passwords still work: nothing was reset.
        self.assertTrue(
            self.client.login(username="ta_owner", password=first["ta_owner"])
        )

    def test_only_missing_accounts_are_created(self):
        run("--allow-production")
        User.objects.get(username="team3_owner").delete()
        passwords = printed_passwords(run("--allow-production"))
        self.assertEqual(list(passwords), ["team3_owner"])
        self.assertTrue(
            Pet.objects.filter(owner__username="team3_owner", name="Milo").exists()
        )

    def test_existing_account_with_another_role_stops_everything(self):
        taken = User.objects.create_user(
            username="team2_owner", password="x-Taken-pass-9"
        )
        AccountProfile.objects.update_or_create(
            user=taken, defaults={"role": AccountProfile.Role.CAREGIVER}
        )
        with self.assertRaisesMessage(CommandError, "team2_owner already exists"):
            run("--allow-production")
        # One transaction: the accounts made before team2 were rolled back too.
        self.assertFalse(User.objects.filter(username="prof_owner").exists())
        self.assertFalse(CaregiverProfile.objects.exists())

    def test_existing_account_without_a_profile_stops_everything(self):
        user = User.objects.create_user(
            username="prof_caregiver", password="x-Taken-pass-9"
        )
        AccountProfile.objects.filter(user=user).delete()
        with self.assertRaisesMessage(CommandError, "missing or different role"):
            run("--allow-production")
        self.assertFalse(User.objects.filter(username="prof_owner").exists())
