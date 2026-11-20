import base64
import json
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.management.commands.create_testing_party import EVALUATORS


class Command(BaseCommand):
    help = "Apply testing-party passwords on PawPal integration only."

    def handle(self, *args, **options):
        expected_host = "pawpal-integration.us-east-2.elasticbeanstalk.com"

        if (
            settings.DEBUG
            or settings.ALLOWED_HOSTS != [expected_host]
            or os.environ.get("TESTING_PARTY_APPLY") != "yes"
        ):
            raise CommandError("This command is restricted to integration.")

        encoded = os.environ.get("TESTING_PARTY_CREDENTIALS_B64")
        if not encoded:
            raise CommandError("Missing testing-party credentials.")

        try:
            raw = base64.b64decode(encoded, validate=True)
            credentials = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise CommandError("Invalid credentials payload.") from exc

        expected = {
            f"{prefix}_{suffix}"
            for prefix, *_ in EVALUATORS
            for suffix in ("owner", "caregiver")
        }

        if not isinstance(credentials, dict) or set(credentials) != expected:
            raise CommandError("Expected exactly 14 testing-party accounts.")
        if not all(
            isinstance(password, str) and password for password in credentials.values()
        ):
            raise CommandError("Invalid password in payload.")

        User = get_user_model()

        with transaction.atomic():
            for username, password in credentials.items():
                if not isinstance(password, str) or not password:
                    raise CommandError("Invalid password in payload.")

                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist as exc:
                    raise CommandError(
                        f"Missing account: {username}. Run account seeding first."
                    ) from exc

                user.set_password(password)
                user.save(update_fields=["password"])

        self.stdout.write(
            self.style.SUCCESS("Updated 14 integration testing-party passwords.")
        )
