from django.db import migrations


def activate_picked_services(apps, schema_editor):
    """Services picked on the profile form used to be saved switched off and
    without a price until the caregiver priced them. They now count as offered
    right away, so switch those on. Priced services the caregiver turned off
    themselves stay off."""
    CaregiverService = apps.get_model("caregivers", "CaregiverService")
    CaregiverService.objects.filter(is_active=False, price__isnull=True).update(
        is_active=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("caregivers", "0008_pet_care_skills"),
    ]

    operations = [
        migrations.RunPython(activate_picked_services, migrations.RunPython.noop),
    ]
