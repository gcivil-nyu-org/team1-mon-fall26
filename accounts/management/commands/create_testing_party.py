
import secrets
import string

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AccountProfile
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


def generate_password(length=20):
    """Generate a random password for a demo account."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = "Create PawPal testing-party accounts and sample pets."

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
                self.stdout.write(f"\n{label}")

                for suffix, role in [
                    ("owner", AccountProfile.Role.PET_OWNER),
                    ("caregiver", AccountProfile.Role.CAREGIVER),
                ]:
                    username = f"{prefix}_{suffix}"

                    if dry_run:
                        self.stdout.write(f"  PLAN: {username}")
                        continue

                    user = User.objects.filter(
                        username=username
                    ).first()

                    if user is not None:
                        profile = AccountProfile.objects.filter(
                            user=user
                        ).first()

                        if profile is None or profile.role != role:
                            raise CommandError(
                                f"{username} already exists with "
                                "a missing or different role. "
                                "No changes committed."
                            )

                        self.stdout.write(
                            f"  EXISTS: {username}"
                        )
                        continue

                    password = generate_password()

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
                    self.stdout.write(
                        f"  PLAN: {pet_name} ({pet_type_name})"
                    )
                    continue

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
                self.stdout.write(
                    f"  {status} PET: {pet.name}"
                )

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

        if credentials:
            self.stdout.write(
                "\nNEW ACCOUNT CREDENTIALS — SAVE PRIVATELY"
            )
            for username, password in credentials:
                self.stdout.write(f"{username}: {password}")

            self.stdout.write(
                "\nPasswords are shown only when accounts "
                "are first created. Existing passwords "
                "are never displayed or reset."
            )
