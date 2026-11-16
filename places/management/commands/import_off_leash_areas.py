import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places.models import Place
from places.nyc_open_data import OpenDataUnavailable, download
from places.off_leash import DATASET_URL, DIRECTORY_URL, off_leash_areas, properties_url

FIELDS = (
    "name",
    "address",
    "neighborhood",
    "borough",
    "zip_code",
    "latitude",
    "longitude",
    "hours",
    "features",
)


@transaction.atomic
def update_off_leash_areas(rows, checked_on):
    """Add new off-leash areas, update changed ones and hide those NYC Parks
    no longer lists. Areas an admin edited on the "Pet-friendly places" page
    are left as the admin set them. Returns (added, updated, hidden)."""
    existing = {
        p.source_id: p
        for p in Place.objects.filter(source=Place.Source.NYC_PARKS_DOG_AREAS)
    }
    added = updated = 0
    for row in rows:
        place = existing.pop(row["source_id"], None)
        if place is not None and place.edited_at is not None:
            continue
        if place is None:
            Place.objects.create(
                category=Place.Category.OFF_LEASH,
                source=Place.Source.NYC_PARKS_DOG_AREAS,
                source_id=row["source_id"],
                checked_on=checked_on,
                **{field: row[field] for field in FIELDS},
            )
            added += 1
            continue
        for field in FIELDS:
            setattr(place, field, row[field])
        place.checked_on = checked_on
        place.is_active = True
        place.save()
        updated += 1
    hidden = Place.objects.filter(
        pk__in=[p.pk for p in existing.values()], is_active=True, edited_at=None
    ).update(is_active=False)
    return added, updated, hidden


class Command(BaseCommand):
    help = (
        "Update the off-leash areas on the Explore map from NYC Parks' dog areas "
        f"directory ({DATASET_URL}), placed with NYC Parks' Parks Properties."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--directory", help="Read the dog areas directory from a JSON file."
        )
        parser.add_argument(
            "--properties",
            help="Read the Parks Properties rows from a JSON file saved from the API.",
        )

    def _load(self, path, url):
        if path:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        try:
            return download(url)
        except OpenDataUnavailable as error:
            raise CommandError(f"Couldn't reach NYC Parks, nothing changed: {error}")

    def handle(self, *args, **options):
        directory = self._load(options["directory"], DIRECTORY_URL)
        if not isinstance(directory, list):
            raise CommandError("NYC Parks sent something unexpected.")
        prop_ids = {
            (entry.get("Prop_ID") or "").strip()
            for entry in directory
            if (entry.get("DogRuns_Type") or "").strip().lower() == "off-leash"
        } - {""}
        if not prop_ids:
            raise CommandError("No off-leash areas found, nothing changed.")
        properties = self._load(options["properties"], properties_url(prop_ids))
        if not isinstance(properties, list):
            raise CommandError("NYC Open Data sent something unexpected.")
        places = off_leash_areas(directory, properties)
        if not places:
            raise CommandError("No off-leash areas could be placed, nothing changed.")
        added, updated, hidden = update_off_leash_areas(places, timezone.localdate())
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(places)} off-leash areas from NYC Parks: "
                f"{added} added, {updated} updated, {hidden} no longer listed."
            )
        )
