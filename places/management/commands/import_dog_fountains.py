import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places.dog_fountains import API_URL, DATASET_URL, dog_fountains
from places.models import Place
from places.nyc_open_data import OpenDataUnavailable, download

FIELDS = ("name", "neighborhood", "borough", "latitude", "longitude", "features")


@transaction.atomic
def update_dog_fountains(rows, checked_on):
    """Add new dog fountains, update changed ones and hide those NYC Parks no
    longer lists as working. Fountains an admin edited on the "Pet-friendly
    places" page are left as the admin set them. Returns (added, updated, hidden)."""
    existing = {
        p.source_id: p
        for p in Place.objects.filter(source=Place.Source.NYC_PARKS_FOUNTAINS)
    }
    added = updated = 0
    for row in rows:
        place = existing.pop(row["source_id"], None)
        if place is not None and place.edited_at is not None:
            continue
        if place is None:
            Place.objects.create(
                category=Place.Category.DOG_FOUNTAIN,
                source=Place.Source.NYC_PARKS_FOUNTAINS,
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
        "Update the dog fountains on the Explore map from NYC Parks' Drinking "
        f"Fountains on NYC Open Data ({DATASET_URL})."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            help="Read a JSON file saved from the dataset's API instead of "
            "downloading it.",
        )

    def handle(self, *args, **options):
        if options["file"]:
            with open(options["file"], encoding="utf-8") as f:
                data = json.load(f)
        else:
            try:
                data = download(API_URL)
            except OpenDataUnavailable as error:
                raise CommandError(
                    f"Couldn't reach NYC Open Data, nothing changed: {error}"
                )
        if not isinstance(data, list):
            raise CommandError("NYC Open Data sent something unexpected.")
        places = dog_fountains(data)
        if not places:
            raise CommandError("No dog fountains found in the data, nothing changed.")
        added, updated, hidden = update_dog_fountains(places, timezone.localdate())
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(places)} dog fountains from NYC Parks: "
                f"{added} added, {updated} updated, {hidden} no longer working."
            )
        )
