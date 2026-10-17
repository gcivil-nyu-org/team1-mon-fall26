from django.db import migrations

# Matches the "Type of pet" options in the UI design.
DEFAULT_PET_TYPES = ["Dog", "Cat", "Bird", "Rabbit", "Fish", "Other"]


def add_pet_types(apps, schema_editor):
    """Give every database the same starting pet types (admins can add more)."""
    PetType = apps.get_model("pets", "PetType")
    for name in DEFAULT_PET_TYPES:
        PetType.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("pets", "0003_pet_owner"),
    ]

    operations = [
        migrations.RunPython(add_pet_types, migrations.RunPython.noop),
    ]
