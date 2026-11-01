import time

from django.core.management.base import BaseCommand

from caregivers.geocoding import GeocodingUnavailable, geocode
from caregivers.models import CaregiverProfile


class Command(BaseCommand):
    help = "Look up map coordinates for caregivers who have an address but no coordinates yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Look up every caregiver with an address, not only the missing ones.",
        )

    def handle(self, *args, **options):
        caregivers = CaregiverProfile.objects.exclude(address="")
        if not options["all"]:
            caregivers = caregivers.filter(latitude__isnull=True)

        found = not_found = 0
        for caregiver in caregivers:
            try:
                location = geocode(caregiver.address)
            except GeocodingUnavailable as error:
                self.stderr.write(f"GeoSearch is unavailable, stopping: {error}")
                break
            if location is None:
                not_found += 1
                self.stdout.write(f"Not found: caregiver #{caregiver.pk}")
            else:
                caregiver.latitude = location.latitude
                caregiver.longitude = location.longitude
                caregiver.neighborhood = location.neighborhood
                caregiver.save(update_fields=["latitude", "longitude", "neighborhood"])
                found += 1
            time.sleep(0.2)  # be gentle with the free public service

        self.stdout.write(
            self.style.SUCCESS(f"Updated {found}, not found {not_found}.")
        )
