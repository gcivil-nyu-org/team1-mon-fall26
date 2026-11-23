"""The database cache's table (settings.CACHES), so `migrate` creates it on
every machine and on Elastic Beanstalk without an extra command."""

from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_account_profile_forum_restricted_at"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
