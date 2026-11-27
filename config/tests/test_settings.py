"""The settings read deployment values from environment variables.

Each case loads config.settings in a fresh Python process with a given
environment, since settings are only read once per process."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

# This file lives in config/tests/, so the project root is three levels up.
BASE_DIR = Path(__file__).resolve().parents[2]

SCRIPT = (
    "import json, os, sys, warnings\n"
    "sys.argv = os.environ.get('TEST_ARGV', 'manage.py').split()\n"
    "with warnings.catch_warnings(record=True) as caught:\n"
    "    warnings.simplefilter('always')\n"
    "    from config import settings as s\n"
    "print(json.dumps({'debug': s.DEBUG, 'secret': s.SECRET_KEY,\n"
    "    'https': s.HTTPS,\n"
    "    'secure_cookies': getattr(s, 'SESSION_COOKIE_SECURE', False),\n"
    "    'csrf_secure': getattr(s, 'CSRF_COOKIE_SECURE', False),\n"
    "    'ssl_redirect': getattr(s, 'SECURE_SSL_REDIRECT', False),\n"
    "    'hsts': getattr(s, 'SECURE_HSTS_SECONDS', 0),\n"
    "    'trusted': getattr(s, 'CSRF_TRUSTED_ORIGINS', []),\n"
    "    'hosts': s.ALLOWED_HOSTS, 'db': s.DATABASES['default'],\n"
    "    'mail': s.MAILERS['default'],\n"
    "    'warnings': [str(w.message) for w in caught]}, default=str))\n"
)

DEPLOY_VARS = (
    "DJANGO_DEBUG",
    "DJANGO_SECRET_KEY",
    "DJANGO_SECRET_KEY_FILE",
    "DJANGO_HTTPS",
    "DJANGO_HSTS_SECONDS",
    "TEST_ARGV",
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
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.key_file = Path(tmp.name) / "secret_key"

    def load(self, **env):
        return load_settings(DJANGO_SECRET_KEY_FILE=str(self.key_file), **env)

    def test_local_defaults(self):
        s = self.load(TEST_ARGV="manage.py runserver")
        self.assertTrue(s["debug"])
        self.assertFalse(s["https"])
        self.assertEqual(s["db"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(s["warnings"], [])

    def test_debug_is_off_unless_running_the_dev_server(self):
        # #316: gunicorn or any other command without DJANGO_DEBUG.
        self.assertFalse(self.load(TEST_ARGV="gunicorn config.wsgi")["debug"])
        self.assertFalse(self.load()["debug"])
        self.assertTrue(self.load(DJANGO_DEBUG="True")["debug"])

    def test_without_a_secret_key_a_random_one_is_kept_on_the_machine(self):
        # #316: no committed key; the same key every time on this machine.
        first = self.load()["secret"]
        self.assertGreaterEqual(len(first), 40)
        self.assertNotIn("django-insecure", first)
        self.assertEqual(self.key_file.read_text(), first)
        self.assertEqual(self.key_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.load()["secret"], first)
        other = Path(self.key_file.parent) / "other_key"
        self.assertNotEqual(
            load_settings(DJANGO_SECRET_KEY_FILE=str(other))["secret"], first
        )

    def test_https_settings(self):
        # #315: off while the site is on plain HTTP, all on with DJANGO_HTTPS.
        s = self.load()
        self.assertFalse(s["secure_cookies"] or s["ssl_redirect"] or s["hsts"])
        s = self.load(DJANGO_HTTPS="True")
        self.assertTrue(s["secure_cookies"] and s["csrf_secure"] and s["ssl_redirect"])
        self.assertEqual(s["hsts"], 3600)
        self.assertIn(
            "https://pawpal-env.eba-x2trrt2m.us-east-2.elasticbeanstalk.com",
            s["trusted"],
        )

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


class ElasticBeanstalkSecretKeyTests(SimpleTestCase):
    """#316: the server's own key is made, owned by the web app's user, before
    collectstatic or migrate load the settings as root."""

    def test_deploy_makes_the_key_before_any_manage_command(self):
        static = (BASE_DIR / ".ebextensions" / "01_static.config").read_text()
        self.assertLess(static.index("00_secret_key"), static.index("collectstatic"))
        self.assertIn("chown webapp:webapp /var/app/data/secret_key", static)


class ElasticBeanstalkStaticFilesTests(SimpleTestCase):
    """Bug report: the live site showed no CSS. nginx was told to serve
    /static itself and answered 404, so WhiteNoise has to serve it."""

    def test_static_is_served_by_whitenoise_not_nginx(self):
        static = (BASE_DIR / ".ebextensions" / "01_static.config").read_text()
        self.assertNotIn("/static:", static)
        self.assertIn("/media: media", static)
        self.assertIn("collectstatic --noinput", static)
        self.assertIn(
            "whitenoise.middleware.WhiteNoiseMiddleware",
            (BASE_DIR / "config" / "settings.py").read_text(),
        )


class EmailSettingsTests(SimpleTestCase):
    """Password reset emails (#46): printed locally, sent by SMTP on a server."""

    def test_emails_are_printed_locally(self):
        mail = load_settings()["mail"]
        self.assertEqual(mail["BACKEND"], "accounts.console_mail.EmailBackend")

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


class TestSpeedTests(SimpleTestCase):
    """Only the test run uses the fast password hasher."""

    def test_tests_use_the_fast_hasher(self):
        from django.conf import settings

        self.assertEqual(
            settings.PASSWORD_HASHERS,
            ["django.contrib.auth.hashers.MD5PasswordHasher"],
        )

    def test_the_site_keeps_the_secure_default(self):
        script = (
            "from config import settings as s; "
            "print(getattr(s, 'PASSWORD_HASHERS', 'default'))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "default")
