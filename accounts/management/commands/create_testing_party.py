
import csv
import os
import secrets
import string
from pathlib import Path

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


INTEGRATION_HOST = "pawpal-integration.us-east-2.elasticbeanstalk.com"


def generate_password(length=20):
    """Generate a random password for local demo accounts."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def load_demo_passwords(csv_path):
    """Read and validate the existing testing-party CSV."""
    if not csv_path.is_file():
        raise CommandError(f"Credentials file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        if not {"username", "password"}.issubset(reader.fieldnames or []):
            raise CommandError("CSV must contain username,password columns.")

        rows = list(reader)

    expected = {
        f"{prefix}_{suffix}"
        for prefix, *_ in EVALUATORS
        for suffix in ("owner", "caregiver")
    }

    passwords = {}

    for row in rows:
        username = row["username"]
        password = row["password"]

        if username in passwords:
            raise CommandError(f"Duplicate username: {username}")

        if not password:
            raise CommandError(f"Empty password for {username}")

        passwords[username] = password

    if len(rows) != 14 or set(passwords) != expected:
        raise CommandError(
            "Credentials CSV must contain exactly the 14 expected demo accounts."
        )

    return passwords


class Command(BaseCommand):
    help = "Create or update PawPal testing-party accounts and sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without modifying the database.",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Allow DEBUG=False, subject to integration safety checks.",
        )
        parser.add_argument(
            "--credentials-file",
            type=Path,
            help="CSV containing the 14 existing demo usernames and passwords.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        csv_path = options["credentials_file"]

        if not settings.DEBUG and not dry_run:
            if not options["allow_production"]:
                raise CommandError(
                    "DEBUG=False requires --allow-production."
                )

            # Check the deployment's explicitly configured hostname rather than
            # requiring Django ALLOWED_HOSTS to be an exact one-item list.
            if os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip() != INTEGRATION_HOST:
                raise CommandError(
                    "Refusing to modify a non-integration environment."
                )

        passwords = load_demo_passwords(csv_path) if csv_path else None

        if not settings.DEBUG and not dry_run and passwords is None:
            raise CommandError(
                "Integration setup requires --credentials-file."
            )

        User = get_user_model()
        generated_credentials = []

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
                                f"{username} has a missing or incorrect role. "
                                "No changes committed."
                            )

                        if passwords is not None:
                            user.set_password(passwords[username])
                            user.save(update_fields=["password"])
                            self.stdout.write(f"  UPDATED: {username}")
                        else:
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

                    if passwords is None:
                        generated_credentials.append((username, password))

                    self.stdout.write(f"  CREATED: {username}")

                if dry_run:
                    self.stdout.write(
                        f"  PLAN: Caregiver profile for {caregiver_name}"
                    )
                    self.stdout.write(
                        f"  PLAN: {pet_name} ({pet_type_name})"
                    )
                    continue

                caregiver = User.objects.get(
                    username=f"{prefix}_caregiver"
                )

                caregiver_profile, profile_created = (
                    CaregiverProfile.objects.get_or_create(
                        user=caregiver,
                        defaults={
                            "name": caregiver_name,
                            "bio": caregiver_bio,
                        },
                    )
                )

                profile_status = (
                    "CREATED" if profile_created else "EXISTS"
                )

                self.stdout.write(
                    f"  {profile_status} CAREGIVER PROFILE: "
                    f"{caregiver_profile.name}"
                )

                owner = User.objects.get(
                    username=f"{prefix}_owner"
                )

                pet_type, _ = PetType.objects.get_or_create(
                    name=pet_type_name
                )

                pet, created = Pet.objects.get_or_create(
                    owner=owner,
                    name=pet_name,
                    defaults={"pet_type": pet_type},
                )

                status = "CREATED" if created else "EXISTS"
                self.stdout.write(f"  {status} PET: {pet.name}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY RUN — No database changes made."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS("\nSetup completed successfully.")
        )

        if passwords is not None:
            self.stdout.write(
                self.style.SUCCESS(
                    "All 14 demo accounts have their CSV passwords."
                )
            )

        if generated_credentials:
            self.stdout.write(
                "\nNEW ACCOUNT CREDENTIALS — SAVE PRIVATELY"
            )

            for username, password in generated_credentials:
                self.stdout.write(f"{username}: {password}")
