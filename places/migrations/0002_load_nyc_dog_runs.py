"""Load the dog parks from the NYC Open Data snapshot in places/data, so every
copy of PawPal has them right after `migrate`. Refresh them from NYC Open Data
any time with `python manage.py import_dog_runs`."""

import json
from datetime import date
from pathlib import Path

from django.db import migrations

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "nyc_dog_runs.json"


def load(apps, schema_editor):
    Place = apps.get_model("places", "Place")
    with SNAPSHOT.open(encoding="utf-8") as f:
        snapshot = json.load(f)
    checked_on = date.fromisoformat(snapshot["downloaded"])
    for run in snapshot["dog_runs"]:
        Place.objects.update_or_create(
            source="nyc_parks",
            source_id=run["source_id"],
            defaults={
                "category": "dog_park",
                "checked_on": checked_on,
                **{k: v for k, v in run.items() if k != "source_id"},
            },
        )


def unload(apps, schema_editor):
    apps.get_model("places", "Place").objects.filter(source="nyc_parks").delete()


class Migration(migrations.Migration):
    dependencies = [("places", "0001_initial")]

    operations = [migrations.RunPython(load, unload)]
