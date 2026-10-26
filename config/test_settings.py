"""The settings read deployment values from environment variables.

Each case loads config.settings in a fresh Python process with a given
environment, since settings are only read once per process."""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent

SCRIPT = (
    "import json, warnings\n"
    "with warnings.catch_warnings(record=True) as caught:\n"
    "    warnings.simplefilter('always')\n"
    "    from config import settings as s\n"
    "print(json.dumps({'debug': s.DEBUG, 'secret': s.SECRET_KEY,\n"
    "    'dev_secret': s.SECRET_KEY == s.DEV_SECRET_KEY,\n"
    "    'hosts': s.ALLOWED_HOSTS, 'db': s.DATABASES['default'],\n"
    "    'warnings': [str(w.message) for w in caught]}, default=str))\n"
)

DEPLOY_VARS = (
    "DJANGO_DEBUG", "DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS",
    "RDS_HOSTNAME", "RDS_PORT", "RDS_DB_NAME", "RDS_USERNAME", "RDS_PASSWORD",
)


def load_settings(**env):
    clean = {k: v for k, v in os.environ.items() if k not in DEPLOY_VARS}
    clean.update(env)
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=BASE_DIR, env=clean,
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


class SettingsFromEnvironmentTests(SimpleTestCase):
    def test_local_defaults(self):
        s = load_settings()
        self.assertTrue(s["debug"])
        self.assertTrue(s["dev_secret"])
        self.assertEqual(s["db"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(s["warnings"], [])

    def test_production_values(self):
        s = load_settings(
            DJANGO_DEBUG="False",
            DJANGO_SECRET_KEY="a-real-secret",
            DJANGO_ALLOWED_HOSTS="pawpal.example.com, www.pawpal.example.com",
        )
        self.assertFalse(s["debug"])
        self.assertEqual(s["secret"], "a-real-secret")
        self.assertIn("pawpal.example.com", s["hosts"])
        self.assertIn("www.pawpal.example.com", s["hosts"])
        self.assertIn("pawpal-env.eba-x2trrt2m.us-east-2.elasticbeanstalk.com", s["hosts"])
        self.assertEqual(s["warnings"], [])

    def test_warns_when_production_has_no_secret_key(self):
        s = load_settings(DJANGO_DEBUG="False", DJANGO_SECRET_KEY="")
        self.assertTrue(s["dev_secret"])
        self.assertTrue(any("DJANGO_SECRET_KEY" in w for w in s["warnings"]))

    def test_rds_variables_switch_to_postgresql(self):
        s = load_settings(
            RDS_HOSTNAME="db.example.us-east-2.rds.amazonaws.com",
            RDS_DB_NAME="pawpal", RDS_USERNAME="pawpal", RDS_PASSWORD="pw",
        )
        self.assertEqual(s["db"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(s["db"]["HOST"], "db.example.us-east-2.rds.amazonaws.com")
        self.assertEqual(s["db"]["PORT"], "5432")
        self.assertEqual(s["db"]["NAME"], "pawpal")
