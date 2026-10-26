from django.db import migrations


NEW_SERVICE_TYPES = [
    ("Feeding & watering", "Provide fresh food and water according to the pet's routine."),
    ("Overnight care", "Stay overnight to provide supervision and companionship."),
    ("Pet boarding", "Care for a pet in the caregiver's home."),
    ("Doggy daycare", "Provide daytime supervision, activities, and companionship."),
    ("Pet transportation", "Transport pets to appointments or other destinations."),
    ("Grooming", "Provide basic grooming and hygiene care."),
    ("Medication administration", "Administer prescribed medication as instructed."),
    ("House sitting", "Care for pets and their home while the owner is away."),
    ("Pet training", "Provide training and behavioral enrichment."),
    ("Exotic pet care", "Care for exotic pets according to their species-specific needs."),
    ("Reptile care", "Care for reptiles, including feeding and enclosure checks."),
    ("Bird care", "Provide feeding, enrichment, and daily care for birds."),
    ("Small mammal care", "Care for rabbits, guinea pigs, hamsters, and other small mammals."),
    ("Habitat cleaning & maintenance", "Clean and maintain pet enclosures and habitats."),
]


def add_service_types(apps, schema_editor):
    ServiceType = apps.get_model("caregivers", "ServiceType")

    for name, description in NEW_SERVICE_TYPES:
        ServiceType.objects.using(schema_editor.connection.alias).get_or_create(
            name=name,
            defaults={"description": description},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("caregivers", "0006_caregiverprofile_location"),
        ("bookings", "0002_default_service_types"),
    ]

    operations = [
        migrations.RunPython(
            add_service_types,
            migrations.RunPython.noop,
        ),
    ]