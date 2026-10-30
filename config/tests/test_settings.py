"""The settings read deployment values from environment variables.

Each case loads config.settings in a fresh Python process with a given
environment, since settings are only read once per process."""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

# This file lives in config/tests/, so the project root is three levels up.
BASE_DIR = Path(__file__).resolve().parents[2]

SCRIPT = (
    "import json, warnings\n"
    "with warnings.catch_warnings(record=True) as caught:\n"
    "    warnings.simplefilter('always')\n"
    "    from config import settings as s\n"
    "print(json.dumps({'debug': s.DEBUG, 'secret': s.SECRET_KEY,\n"
    "    'dev_secret': s.SECRET_KEY == s.DEV_SECRET_KEY,\n"
    "    'hosts': s.ALLOWED_HOSTS, 'db': s.DATABASES['default'],\n"
    "    'mail': s.MAILERS['default'],\n"
    "    'warnings': [str(w.message) for w in caught]}, default=str))\n"
)

DEPLOY_VARS = (
    "DJANGO_DEBUG",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "RDS_HOSTNAME",
    "RDS_PORT",
    "RDS_DB_NAME",
    "RDS_USERNAME",
    "RDS_PASSWORD",
    "SQLITE_DB_PATH",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
)


def load_settings(**env):
    clean = {k: v for k, v in os.environ.items() if k not in DEPLOY_VARS}
    clean.update(env)
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=BASE_DIR,
        env=clean,
        capture_output=True,
        text=True,
        check=True,
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
        self.assertIn(
            "pawpal-env.eba-x2trrt2m.us-east-2.elasticbeanstalk.com", s["hosts"]
        )
        self.assertEqual(s["warnings"], [])

    def test_warns_when_production_has_no_secret_key(self):
        s = load_settings(DJANGO_DEBUG="False", DJANGO_SECRET_KEY="")
        self.assertTrue(s["dev_secret"])
        self.assertTrue(any("DJANGO_SECRET_KEY" in w for w in s["warnings"]))

    def test_rds_variables_switch_to_postgresql(self):
        s = load_settings(
            RDS_HOSTNAME="db.example.us-east-2.rds.amazonaws.com",
            RDS_DB_NAME="pawpal",
            RDS_USERNAME="pawpal",
            RDS_PASSWORD="pw",
        )
        self.assertEqual(s["db"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(s["db"]["HOST"], "db.example.us-east-2.rds.amazonaws.com")
        self.assertEqual(s["db"]["PORT"], "5432")
        self.assertEqual(s["db"]["NAME"], "pawpal")

    def test_sqlite_path_from_environment(self):
        self.assertEqual(load_settings()["db"]["NAME"], str(BASE_DIR / "db.sqlite3"))
        s = load_settings(SQLITE_DB_PATH="/var/app/data/db.sqlite3")
        self.assertEqual(s["db"]["NAME"], "/var/app/data/db.sqlite3")


class ElasticBeanstalkDatabaseTests(SimpleTestCase):
    """Bug report: pets and bookings disappeared from the live site. The
    SQLite file has to live outside /var/app/current, which each deploy
    replaces, so the deploy config sets SQLITE_DB_PATH to the file that
    02_database.config prepares."""

    def test_deploy_config_keeps_the_database_outside_the_app_folder(self):
        static = (BASE_DIR / ".ebextensions" / "01_static.config").read_text()
        database = (BASE_DIR / ".ebextensions" / "02_database.config").read_text()
        self.assertIn("SQLITE_DB_PATH: /var/app/data/db.sqlite3", static)
        self.assertIn("touch /var/app/data/db.sqlite3", database)


class EmailSettingsTests(SimpleTestCase):
    """Password reset emails (#46): printed locally, sent by SMTP on a server."""

    def test_emails_are_printed_locally(self):
        mail = load_settings()["mail"]
        self.assertEqual(
            mail["BACKEND"], "django.core.mail.backends.console.EmailBackend"
        )

    def test_smtp_when_email_host_is_set(self):
        mail = load_settings(
            EMAIL_HOST="smtp.example.com",
            EMAIL_HOST_USER="pawpal@example.com",
            EMAIL_HOST_PASSWORD="app-password",
        )["mail"]
        self.assertEqual(mail["BACKEND"], "django.core.mail.backends.smtp.EmailBackend")
        self.assertEqual(mail["OPTIONS"]["host"], "smtp.example.com")
        self.assertEqual(mail["OPTIONS"]["port"], 587)
        self.assertEqual(mail["OPTIONS"]["username"], "pawpal@example.com")
        self.assertTrue(mail["OPTIONS"]["use_tls"])
