from django.db import migrations


NEW_PET_TYPES = [
    "Guinea pig",
    "Hamster",
    "Gerbil",
    "Ferret",
    "Chinchilla",
    "Rat",
    "Mouse",
    "Hedgehog",
    "Snake",
    "Gecko",
    "Lizard",
    "Turtle",
    "Tortoise",
    "Frog",
    "Salamander",
    "Tarantula",
    "Invertebrate",
    "Other",
]


def add_pet_types(apps, schema_editor):
    PetType = apps.get_model("pets", "PetType")

    for name in NEW_PET_TYPES:
        PetType.objects.using(schema_editor.connection.alias).get_or_create(
            name=name
        )


class Migration(migrations.Migration):

    dependencies = [
    ("pets", "0005_pet_care_information"),
    ]

    operations = [
        migrations.RunPython(
            add_pet_types,
            migrations.RunPython.noop,
        ),
    ]