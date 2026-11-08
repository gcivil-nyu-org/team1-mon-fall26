from datetime import datetime, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from reports.templatetags.report_tags import posted_ago, when_long, when_short


class ReportDateTests(SimpleTestCase):
    def at(self, days_ago, hour=13, minute=5):
        day = timezone.localdate() - timedelta(days=days_ago)
        return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))

    def test_today(self):
        self.assertEqual(when_short(self.at(0)), "1:05 PM")
        self.assertEqual(when_long(self.at(0)), "Today, 1:05 PM")
        self.assertEqual(posted_ago(self.at(0)), "Posted today")

    def test_yesterday(self):
        self.assertEqual(when_short(self.at(1, 18, 40)), "Yesterday")
        self.assertEqual(when_long(self.at(1, 18, 40)), "Yesterday, 6:40 PM")
        self.assertEqual(posted_ago(self.at(1)), "Posted yesterday")

    def test_older(self):
        old = self.at(10)
        label = f"{old:%b} {old.day}"
        self.assertEqual(when_short(old), label)
        self.assertEqual(when_long(old), f"{label}, 1:05 PM")
        self.assertEqual(posted_ago(old), f"Posted {label}")

    def test_empty(self):
        self.assertEqual(when_short(None), "")
        self.assertEqual(when_long(None), "")
        self.assertEqual(posted_ago(None), "")
