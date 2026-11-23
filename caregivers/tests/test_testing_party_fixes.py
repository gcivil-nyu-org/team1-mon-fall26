"""Fixes for issues other teams found at the testing party: editing a service
into one already listed (#323, #344), availability on past days (#324, #348)
and today's availability before now (#343)."""

import json
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.models import (
    CaregiverAvailability,
    CaregiverProfile,
    CaregiverService,
    ServiceType,
)

User = get_user_model()
SAVE_URL = reverse("save_availability_changes")


class FixData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sitter = User.objects.create_user("sitter", password="pw-12345!")
        cls.caregiver = CaregiverProfile.objects.create(
            user=cls.sitter, name="Chloe Shih", service_area="Park Slope"
        )
        cls.walking = ServiceType.objects.get_or_create(name="Dog walking")[0]
        cls.drop_in = ServiceType.objects.get_or_create(name="Drop-in visit")[0]

    def setUp(self):
        self.client.force_login(self.sitter)


class EditServiceDuplicateTests(FixData):
    def setUp(self):
        super().setUp()
        self.walk = CaregiverService.objects.create(
            caregiver=self.caregiver, service_type=self.walking, price=25
        )
        CaregiverService.objects.create(
            caregiver=self.caregiver, service_type=self.drop_in, price=30
        )
        self.url = reverse(
            "edit_caregiver_service", args=[self.caregiver.pk, self.walk.pk]
        )

    def data(self, service_type):
        return {
            "service_type": service_type.pk,
            "price_unit": "hour",
            "price": "25.00",
            "description": "",
            "is_active": "on",
        }

    def test_changing_to_a_listed_type_is_a_form_error(self):
        response = self.client.post(self.url, self.data(self.drop_in))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You already have this service!")
        self.walk.refresh_from_db()
        self.assertEqual(self.walk.service_type, self.walking)

    def test_keeping_the_same_type_still_saves(self):
        response = self.client.post(self.url, self.data(self.walking))
        self.assertRedirects(
            response,
            reverse("services", args=[self.caregiver.pk]),
            fetch_redirect_response=False,
        )


class PastAvailabilityTests(FixData):
    def save(self, day, start="09:00", end="10:00"):
        return self.client.post(
            SAVE_URL,
            json.dumps(
                {
                    "changes": [
                        {
                            "action": "create",
                            "date": day.isoformat(),
                            "start": start,
                            "end": end,
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

    def test_past_day_is_refused(self):
        response = self.save(timezone.localdate() - timedelta(days=1))
        self.assertEqual(response.status_code, 400)
        self.assertIn("day that has passed", response.json()["error"])
        self.assertFalse(CaregiverAvailability.objects.exists())

    def test_long_ago_is_refused(self):
        self.assertEqual(self.save(date(2020, 1, 1)).status_code, 400)

    def test_future_day_still_saves(self):
        response = self.save(timezone.localdate() + timedelta(days=2))
        self.assertEqual(response.json(), {"ok": True})

    def test_updating_a_slot_into_the_past_is_refused(self):
        slot = CaregiverAvailability.objects.create(
            caregiver=self.caregiver,
            date=timezone.localdate() + timedelta(days=2),
            start_time=time(9),
            end_time=time(10),
        )
        yesterday = timezone.localdate() - timedelta(days=1)
        response = self.client.post(
            SAVE_URL,
            json.dumps(
                {
                    "changes": [
                        {
                            "action": "update",
                            "id": slot.pk,
                            "date": yesterday.isoformat(),
                            "start": "09:00",
                            "end": "10:00",
                        }
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_today_already_over_is_refused(self):
        noon = timezone.make_aware(datetime.combine(timezone.localdate(), time(12)))
        with mock.patch("django.utils.timezone.now", return_value=noon):
            self.assertEqual(
                self.save(timezone.localdate(), "08:00", "11:00").status_code, 400
            )
            self.assertEqual(
                self.save(timezone.localdate(), "13:00", "15:00").status_code, 200
            )

    def test_model_clean(self):
        slot = CaregiverAvailability(
            caregiver=self.caregiver,
            date=timezone.localdate() - timedelta(days=3),
            start_time=time(9),
            end_time=time(10),
        )
        with self.assertRaises(ValidationError):
            slot.full_clean()


class PublicAvailabilityTests(FixData):
    def public_slots(self):
        owner = User.objects.create_user("owner", password="pw-12345!")
        self.client.force_login(owner)
        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        return json.loads(response.context["public_availability_json"])

    def test_past_days_and_past_hours_are_not_offered(self):
        today = timezone.localdate()
        noon = timezone.make_aware(datetime.combine(today, time(12, 30)))
        CaregiverAvailability.objects.bulk_create(
            [
                CaregiverAvailability(
                    caregiver=self.caregiver,
                    date=today - timedelta(days=1),
                    start_time=time(9),
                    end_time=time(17),
                ),
                CaregiverAvailability(
                    caregiver=self.caregiver,
                    date=today,
                    start_time=time(8),
                    end_time=time(11),
                ),
                CaregiverAvailability(
                    caregiver=self.caregiver,
                    date=today,
                    start_time=time(12),
                    end_time=time(17),
                ),
            ]
        )
        with mock.patch("django.utils.timezone.now", return_value=noon):
            slots = self.public_slots()
        self.assertEqual(
            slots, [{"date": today.isoformat(), "start": "12:30", "end": "17:00"}]
        )
