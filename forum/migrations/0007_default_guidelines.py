"""#105: start the community guidelines with the five rules in Kat's Figma
"Manage Community Guidelines", so the Forum never shows an empty list. Admins
can edit or remove them afterwards."""

from django.db import migrations

RULES = [
    (
        "Be kind",
        "Treat other owners and caregivers with respect. No insults or harassment.",
    ),
    ("Keep it about pets", "Share tips, places and questions about pet care."),
    (
        "No spam or ads",
        "Don’t post deals, links to sell things or repeat the same post.",
    ),
    (
        "Keep personal info private",
        "Don’t share addresses, phone numbers or door codes in posts.",
    ),
    (
        "Report problems",
        "Use Report if something breaks these rules. Admins will review it.",
    ),
]


def add_rules(apps, schema_editor):
    GuidelineRule = apps.get_model("forum", "GuidelineRule")
    if GuidelineRule.objects.exists():
        return
    for position, (title, text) in enumerate(RULES, start=1):
        GuidelineRule.objects.create(title=title, text=text, position=position)


def remove_rules(apps, schema_editor):
    GuidelineRule = apps.get_model("forum", "GuidelineRule")
    GuidelineRule.objects.filter(title__in=[title for title, _ in RULES]).delete()


class Migration(migrations.Migration):
    dependencies = [("forum", "0006_community_guidelines")]

    operations = [migrations.RunPython(add_rules, remove_rules)]
