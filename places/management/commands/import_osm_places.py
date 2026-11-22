import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from places.models import Place
from places.nyc_open_data import OpenDataUnavailable
from places.osm import download, osm_places
from places.search import NAMES

FIELDS = (
    "name",
    "category",
    "address",
    "zip_code",
    "neighborhood",
    "borough",
    "latitude",
    "longitude",
    "weekly_hours",
    "features",
)


@transaction.atomic
def update_osm_places(rows, checked_on):
    """Add new places, update changed ones and hide those no longer on
    OpenStreetMap (closed, or no longer marked dog-friendly). Places an admin
    edited on the "Pet-friendly places" page are left as the admin set them.
    Returns (added, updated, hidden)."""
    existing = {
        p.source_id: p for p in Place.objects.filter(source=Place.Source.OPENSTREETMAP)
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
                    source=Place.Source.OPENSTREETMAP,
                    source_id=row["source_id"],
                    checked_on=checked_on,
                    **{field: row[field] for field in FIELDS},
                )
            )
            continue
        for field in FIELDS:
            setattr(place, field, row[field])
        place.checked_on = checked_on
        place.is_active = True
        place.save()
        updated += 1
    Place.objects.bulk_create(new, batch_size=500)
    hidden = Place.objects.filter(
        pk__in=[p.pk for p in existing.values()], is_active=True, edited_at=None
    ).update(is_active=False)
    return len(new), updated, hidden


class Command(BaseCommand):
    help = (
        "Update the Explore map's pet stores and dog-friendly cafés and "
        "restaurants from OpenStreetMap (© OpenStreetMap contributors)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            help="Read a JSON file saved from the Overpass API instead of "
            "downloading it.",
        )

    def handle(self, *args, **options):
        if options["file"]:
            with open(options["file"], encoding="utf-8") as f:
                data = json.load(f)
        else:
            try:
                data = download()
            except OpenDataUnavailable as error:
                raise CommandError(
                    f"Couldn't reach OpenStreetMap, nothing changed: {error}"
                )
        if not isinstance(data, dict):
            raise CommandError("OpenStreetMap sent something unexpected.")
        places = osm_places(data)
        if not places:
            raise CommandError("No places found on OpenStreetMap, nothing changed.")
        added, updated, hidden = update_osm_places(places, timezone.localdate())
        counts = {
            category: sum(1 for p in places if p["category"] == category)
            for category in ("cafe", "restaurant", "pet_store")
        }
        summary = ", ".join(
            f"{n} {NAMES[category][0 if n == 1 else 1]}"
            for category, n in counts.items()
            if n
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(places)} places from OpenStreetMap ({summary}): "
                f"{added} added, {updated} updated, {hidden} no longer listed."
            )
        )
