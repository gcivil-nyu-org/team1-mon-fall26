import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places.dining_out import API_URL, DATASET_URL, outdoor_dining
from places.models import Place
from places.nyc_open_data import OpenDataUnavailable, download

FIELDS = ("name", "address", "borough", "zip_code", "latitude", "longitude")


@transaction.atomic
def update_outdoor_dining(rows, checked_on):
    """Add new outdoor dining, update changed places and hide those no longer
    licensed. Places an admin edited on the "Pet-friendly places" page are left
    as the admin set them. Returns (added, updated, hidden)."""
    existing = {
        p.source_id: p for p in Place.objects.filter(source=Place.Source.DINING_OUT)
    }
    new = []
    updated = 0
    for row in rows:
        place = existing.pop(row["source_id"], None)
        if place is not None and place.edited_at is not None:
            continue
        if place is None:
            new.append(
                Place(
                    category=Place.Category.OUTDOOR_DINING,
                    source=Place.Source.DINING_OUT,
                    source_id=row["source_id"],
                    checked_on=checked_on,
                    features=row["features"],
                    **{field: row[field] for field in FIELDS},
                )
            )
            continue
        for field in (*FIELDS, "features"):
            setattr(place, field, row[field])
        place.checked_on = checked_on
        place.is_active = True
        place.save()
        updated += 1
    # Thousands of rows: added in batches rather than one at a time.
    Place.objects.bulk_create(new, batch_size=500)
    hidden = Place.objects.filter(
        pk__in=[p.pk for p in existing.values()], is_active=True, edited_at=None
    ).update(is_active=False)
    return len(new), updated, hidden


class Command(BaseCommand):
    help = (
        "Update outdoor dining on the Explore map from NYC DOT's Dining Out NYC "
        f"licenses on NYC Open Data ({DATASET_URL})."
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
        places = outdoor_dining(data)
        if not places:
            raise CommandError("No outdoor dining found in the data, nothing changed.")
        added, updated, hidden = update_outdoor_dining(places, timezone.localdate())
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(places)} places with outdoor dining from NYC Open Data: "
                f"{added} added, {updated} updated, {hidden} no longer licensed."
            )
        )
