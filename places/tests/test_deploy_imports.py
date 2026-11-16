"""Every NYC Open Data import runs on each deploy. Outdoor dining was added
without its deploy command, so the category stayed empty on the servers."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

COMMANDS = Path(settings.BASE_DIR) / "places" / "management" / "commands"
DEPLOY = Path(settings.BASE_DIR) / ".ebextensions" / "02_database.config"


class DeployImportsTests(SimpleTestCase):
    def test_every_import_runs_on_deploy(self):
        imports = sorted(p.stem for p in COMMANDS.glob("import_*.py"))
        self.assertIn("import_outdoor_dining", imports)
        config = DEPLOY.read_text()
        for name in imports:
            with self.subTest(name):
                # "|| true": NYC Open Data being down mustn't stop a deploy.
                self.assertIn(f'"python manage.py {name} || true"', config)
