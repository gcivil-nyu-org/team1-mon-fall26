"""Story #107: reports of wrong place information on the admin Reports page
(Figma "Pet-Friendly Places Report", "Report Marked as Resolved" and
"Resolved Reports")."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from places.models import Place, PlaceReport
from reports.templatetags.report_tags import open_report_count

User = get_user_model()
LIST_URL = reverse("reports:admin_list")


class PlaceReportData(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.all().delete()
        cls.admin = User.objects.create_user(
            "admin", password="pw-12345!", first_name="Ada", is_staff=True
        )
        cls.kat = User.objects.create_user(
            "kat", password="pw-12345!", first_name="Kat", last_name="Wong"
        )
        cls.chloe = User.objects.create_user(
            "chloe", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        cls.cafe = Place.objects.create(
            name="Bark & Brew Café",
            category="cafe",
            address="214 7th Ave",
            borough="Brooklyn",
            latitude=40.6716,
            longitude=-73.9780,
        )
        cls.patio = Place.objects.create(
            name="Paws Patio", category="restaurant", latitude=40.67, longitude=-73.98
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.older = PlaceReport.objects.create(
            place=self.cafe,
            reporter=self.chloe,
            reason="wrong_hours",
            details="They close at 5 now, not 6.",
        )
        PlaceReport.objects.filter(pk=self.older.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        self.newest = PlaceReport.objects.create(
            place=self.cafe,
            reporter=self.kat,
            reason="wrong_hours",
            details="Hours changed. Now closes at 5 PM.",
        )

    def detail_url(self, report):
        return reverse("reports:admin_place", args=[report.pk])


class PlaceReportListTests(PlaceReportData):
    def test_one_row_per_place(self):
        response = self.client.get(LIST_URL)
        rows = response.context["reports"]
        self.assertEqual(rows, [self.newest])
        self.assertEqual(rows[0].others, 1)
        self.assertEqual(response.context["selected"], self.newest)
        self.assertContains(response, "Place: Bark &amp; Brew Café")
        self.assertContains(response, "Reported by Kat W. +1")
        tabs = {t["key"]: t["count"] for t in response.context["tabs"]}
        self.assertEqual(tabs, {"open": 1, "resolved": 0})
        self.assertEqual(open_report_count(), 1)

    def test_header_count_counts_places_once(self):
        PlaceReport.objects.create(place=self.patio, reporter=self.kat, details="x")
        self.assertEqual(open_report_count(), 2)
        response = self.client.get(LIST_URL)
        self.assertContains(response, '<span class="nav-count">2<span')

    def test_regular_users_are_refused(self):
        self.client.force_login(self.kat)
        self.assertEqual(self.client.get(self.detail_url(self.newest)).status_code, 403)
        resolve = reverse("reports:admin_place_resolve", args=[self.newest.pk])
        self.assertEqual(self.client.post(resolve).status_code, 403)
        self.assertEqual(PlaceReport.objects.filter(status="open").count(), 2)


class PlaceReportDetailTests(PlaceReportData):
    def test_figma_detail(self):
        response = self.client.get(self.detail_url(self.older))
        # The group shows from its newest report, as the row does.
        self.assertEqual(response.context["selected"], self.newest)
        self.assertContains(response, '<h2 id="report-title">Wrong hours</h2>')
        self.assertContains(response, "Place · Reported by Kat W.")
        self.assertContains(response, "2 reports on this place")
        self.assertContains(response, "“Hours changed. Now closes at 5 PM.”")
        self.assertContains(response, "Chloe S. · Yesterday")
        self.assertContains(response, "Open in Explore")
        self.assertContains(
            response, reverse("places:manage_detail", args=[self.cafe.pk])
        )
        self.assertContains(response, "Mark as resolved")
        self.assertContains(response, 'class="report-row is-selected"')

    def test_other_reasons_are_named(self):
        PlaceReport.objects.create(
            place=self.cafe, reporter=self.admin, reason="closed", details="Gone."
        )
        response = self.client.get(self.detail_url(self.newest))
        self.assertContains(response, "Permanently closed")

    def test_mark_as_resolved(self):
        resolve = reverse("reports:admin_place_resolve", args=[self.newest.pk])
        self.assertEqual(self.client.get(resolve).status_code, 405)
        response = self.client.post(resolve)
        self.assertRedirects(
            response,
            self.detail_url(self.newest) + "?done=resolved",
            fetch_redirect_response=False,
        )
        for report in (self.older, self.newest):
            report.refresh_from_db()
            self.assertEqual(report.status, "resolved")
            self.assertEqual(report.resolved_by, self.admin)
        self.assertEqual(self.older.resolved_at, self.newest.resolved_at)

        # Figma "Report Marked as Resolved": still on Open, with the banner.
        response = self.client.get(response.url)
        self.assertEqual(response.context["tab"], "open")
        self.assertContains(response, "Report moved to Resolved.")
        self.assertNotContains(response, "Mark as resolved")
        self.assertEqual(response.context["reports"], [])

        # Figma "Resolved Reports"
        response = self.client.get(LIST_URL, {"status": "resolved"})
        self.assertEqual(response.context["reports"], [self.newest])
        self.assertContains(response, "Resolved</span>")
        response = self.client.get(self.detail_url(self.newest))
        self.assertContains(response, "Resolved by Ada")
        self.assertEqual(response.context["tab"], "resolved")

        # Resolving twice does nothing more.
        response = self.client.post(resolve, follow=True)
        self.assertContains(response, "This report was already handled.")

    def test_new_report_after_resolving_is_its_own_row(self):
        self.newest.resolve(self.admin)
        fresh = PlaceReport.objects.create(
            place=self.cafe, reporter=self.chloe, details="Closed on Mondays."
        )
        response = self.client.get(LIST_URL)
        self.assertEqual(response.context["reports"], [fresh])
        self.assertEqual(len(fresh.group()), 1)

    def test_missing(self):
        url = reverse("reports:admin_place", args=[999])
        self.assertEqual(self.client.get(url).status_code, 404)
