import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places.models import Place
from places.nyc_open_data import (
    DATASET_URL,
    DIRECTORY_URL,
    OpenDataUnavailable,
    dog_runs,
    download,
)

FIELDS = (
    "name",
    "borough",
    "zip_code",
    "neighborhood",
    "latitude",
    "longitude",
    "features",
)


@transaction.atomic
def update_dog_parks(runs, checked_on):
    """Add new dog runs, update changed ones and hide those NYC Parks no longer
    lists. Addresses are only changed when the runs have them (the directory
    was read). Returns (added, updated, hidden)."""
    existing = {
        p.source_id: p for p in Place.objects.filter(source=Place.Source.NYC_PARKS)
    }
    added = updated = 0
    for run in runs:
        place = existing.pop(run["source_id"], None)
        if place is None:
            Place.objects.create(
                category=Place.Category.DOG_PARK,
                source=Place.Source.NYC_PARKS,
                source_id=run["source_id"],
                checked_on=checked_on,
                address=run.get("address", ""),
                **{field: run[field] for field in FIELDS},
            )
            added += 1
        else:
            for field in FIELDS:
                setattr(place, field, run[field])
            if "address" in run:
                place.address = run["address"]
            place.checked_on = checked_on
            place.save()
            updated += 1
    hidden = Place.objects.filter(
        pk__in=[p.pk for p in existing.values()], is_active=True
    ).update(is_active=False)
    return added, updated, hidden


class Command(BaseCommand):
    help = (
        "Update the dog parks on the Explore map from NYC Parks' "
        f"Dog Runs dataset on NYC Open Data ({DATASET_URL})."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            help="Read a GeoJSON file saved from the dataset instead of downloading it.",
        )
        parser.add_argument(
            "--directory",
            help="Read the NYC Parks directory of dog runs (for addresses) from a "
            "saved JSON file instead of downloading it.",
        )

    def handle(self, *args, **options):
        if options["file"]:
            with open(options["file"], encoding="utf-8") as f:
                geojson = json.load(f)
        else:
            try:
                geojson = download()
            except OpenDataUnavailable as error:
                raise CommandError(
                    f"Couldn't reach NYC Open Data, nothing changed: {error}"
                )
        directory = None
        if options["directory"]:
            with open(options["directory"], encoding="utf-8") as f:
                directory = json.load(f)
        elif not options["file"]:
            try:
                directory = download(DIRECTORY_URL)
            except OpenDataUnavailable:
                self.stdout.write(
                    "Couldn't reach the NYC Parks directory of dog runs; "
                    "kept the current addresses."
                )
        runs = dog_runs(geojson, directory)
        if not runs:
            raise CommandError("No dog runs found in the data, nothing changed.")
        added, updated, hidden = update_dog_parks(runs, timezone.localdate())
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(runs)} dog runs from NYC Open Data: "
                f"{added} added, {updated} updated, {hidden} no longer listed."
            )
        )
