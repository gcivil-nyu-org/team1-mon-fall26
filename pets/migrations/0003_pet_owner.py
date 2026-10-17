import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def delete_pets_without_owner(apps, schema_editor):
    """Pets created before owners existed can't be shown to anyone, so remove them."""
    Pet = apps.get_model("pets", "Pet")
    Pet.objects.filter(owner__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pets", "0002_alter_pet_breed_alter_pet_pet_type_alter_pet_photo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pet",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(delete_pets_without_owner, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pet",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="pet",
            options={"ordering": ["name"]},
        ),
        migrations.AlterModelOptions(
            name="pettype",
            options={"ordering": ["name"]},
        ),
    ]
