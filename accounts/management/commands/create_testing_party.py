import secrets
import string
import json
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AccountProfile
from caregivers.models import CaregiverProfile
from pets.models import Pet, PetType

EVALUATORS = [
    ("prof", "Professor", "Mochi", "Cat"),
    ("ta", "Teaching Assistant", "Biscuit", "Dog"),
    ("team1", "Team 1", "Luna", "Dog"),
    ("team2", "Team 2", "Clover", "Rabbit"),
    ("team3", "Team 3", "Milo", "Cat"),
    ("team4", "Team 4", "Sunny", "Bird"),
    ("team5", "Team 5", "Peanut", "Dog"),
]


CAREGIVER_DATA = {
    "prof": (
        "Sophie Bennett",
        "Animal lover with experience caring for dogs and cats "
        "of all personalities. I love long walks, playtime, "
        "and making pets feel at home.",
    ),
    "ta": (
        "Daniel Rivera",
        "Reliable and attentive caregiver who enjoys keeping "
        "pets active, comfortable, and happy while their "
        "owners are away.",
    ),
    "team1": (
        "Emma Collins",
        "I've always loved animals and enjoy getting to know "
        "each pet's unique personality. I'm especially "
        "comfortable caring for cats and smaller pets.",
    ),
    "team2": (
        "Alex Morgan",
        "Patient, dependable, and always excited to meet new "
        "furry friends. I enjoy outdoor activities and making "
        "sure pets get plenty of attention.",
    ),
    "team3": (
        "Olivia Parker",
        "Gentle and detail-oriented caregiver who understands "
        "that every pet has their own routine. Happy to help "
        "with feeding, playtime, and companionship.",
    ),
    "team4": (
        "Noah Mitchell",
        "Passionate about caring for animals of all sizes, "
        "including smaller pets. I prioritize a calm, safe "
        "environment and consistent routines.",
    ),
    "team5": (
        "Maya Thompson",
        "Energetic and caring pet sitter who loves meeting "
        "new animals. I enjoy helping pets stay active and "
        "making sure they feel loved.",
    ),
}


def generate_password(length=20):
    """Generate a random password for a demo account."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = (
        "Create PawPal testing-party accounts, sample pets, " "and caregiver profiles."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the setup without changing the database.",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Explicitly permit running with DEBUG=False.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        passwords_json = os.environ.get("EVALUATOR_PASSWORDS_JSON")
        try:
            passwords = json.loads(passwords_json) if passwords_json else None
        except json.JSONDecodeError as exc:
            raise CommandError("Invalid evaluator password JSON.") from exc

        if passwords is not None:
            expected = {
                f"{prefix}_{suffix}"
                for prefix, *_ in EVALUATORS
                for suffix in ("owner", "caregiver")
            }
            if not isinstance(passwords, dict) or set(passwords) != expected:
                raise CommandError("Invalid evaluator password configuration.")
            if any(not isinstance(p, str) or not p for p in passwords.values()):
                raise CommandError("Invalid evaluator password configuration.")
        if not settings.DEBUG and not dry_run:
            if not options["allow_production"]:
                raise CommandError(
                    "Production changes are blocked. "
                    "Use --allow-production only after review."
                )

        User = get_user_model()
        credentials = []

        self.stdout.write("PawPal Testing Party Setup")
        self.stdout.write("-" * 40)

        with transaction.atomic():
            for prefix, label, pet_name, pet_type_name in EVALUATORS:
                caregiver_name, caregiver_bio = CAREGIVER_DATA[prefix]

                self.stdout.write(f"\n{label}")

                for suffix, role in [
                    ("owner", AccountProfile.Role.PET_OWNER),
                    ("caregiver", AccountProfile.Role.CAREGIVER),
                ]:
                    username = f"{prefix}_{suffix}"

                    if dry_run:
                        self.stdout.write(f"  PLAN: {username}")
                        continue

                    user = User.objects.filter(username=username).first()

                    if user is not None:
                        profile = AccountProfile.objects.filter(user=user).first()

                        if profile is None or profile.role != role:
                            raise CommandError(
                                f"{username} already exists with "
                                "a missing or different role. "
                                "No changes committed."
                            )

                        self.stdout.write(f"  EXISTS: {username}")
                        continue

                    password = (
                        passwords[username]
                        if passwords is not None
                        else generate_password()
                    )

                    user = User.objects.create_user(
                        username=username,
                        password=password,
                    )

                    AccountProfile.objects.update_or_create(
                        user=user,
                        defaults={
                            "role": role,
                            "email_verified": True,
                        },
                    )

                    credentials.append((username, password))
                    self.stdout.write(f"  CREATED: {username}")

                if dry_run:
                    self.stdout.write(f"  PLAN: Caregiver profile for {caregiver_name}")
                    self.stdout.write(f"  PLAN: {pet_name} ({pet_type_name})")
                    continue

                caregiver = User.objects.get(username=f"{prefix}_caregiver")

                caregiver_profile, profile_created = (
                    CaregiverProfile.objects.get_or_create(
                        user=caregiver,
                        defaults={
                            "name": caregiver_name,
                            "bio": caregiver_bio,
                        },
                    )
                )

                profile_status = "CREATED" if profile_created else "EXISTS"

                self.stdout.write(
                    f"  {profile_status} CAREGIVER PROFILE: "
                    f"{caregiver_profile.name}"
                )

                owner = User.objects.get(username=f"{prefix}_owner")

                pet_type, _ = PetType.objects.get_or_create(name=pet_type_name)

                pet, created = Pet.objects.get_or_create(
                    owner=owner,
                    name=pet_name,
                    defaults={"pet_type": pet_type},
                )

                status = "CREATED" if created else "EXISTS"
                self.stdout.write(f"  {status} PET: {pet.name}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN — No database changes made.")
            )
            return

        self.stdout.write(self.style.SUCCESS("\nSetup completed successfully."))

        if credentials and passwords is None:
            self.stdout.write("\nNEW ACCOUNT CREDENTIALS — SAVE PRIVATELY")

            for username, password in credentials:
                self.stdout.write(f"{username}: {password}")

            self.stdout.write(
                "\nPasswords are shown only when accounts "
                "are first created. Existing passwords "
                "are never displayed or reset."
            )
