"""Caregiver availability (#70 Set, #71 Update, #72 View, #73 Reflect bookings):
the caregiver's calendar page, the single-slot edit/delete pages, the batch
save used by the calendar, and the read-only calendar on the public profile."""

import json
from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import CaregiverAvailability, CaregiverProfile, ServiceType
from pets.models import Pet, PetType

User = get_user_model()
MANAGE_URL = reverse("manage_availability")
SAVE_URL = reverse("save_availability_changes")
DAY = date.today() + timedelta(days=7)


class AvailabilityTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sitter = User.objects.create_user("sitter", password="pw-12345!")
        cls.caregiver = CaregiverProfile.objects.create(
            user=cls.sitter, name="Chloe Shih", service_area="Park Slope"
        )
        cls.other_sitter = User.objects.create_user("other", password="pw-12345!")
        cls.other = CaregiverProfile.objects.create(
            user=cls.other_sitter, name="Sam Lee", service_area="Gowanus"
        )
        cls.owner = User.objects.create_user("owner", password="pw-12345!")
        cls.pet = Pet.objects.create(
            owner=cls.owner,
            name="Biscuit",
            pet_type=PetType.objects.get_or_create(name="Dog")[0],
        )
        cls.walk = ServiceType.objects.get(name="Dog walking")

    def setUp(self):
        self.client.force_login(self.sitter)

    def slot(self, start="09:00", end="12:00", day=DAY, caregiver=None):
        return CaregiverAvailability.objects.create(
            caregiver=caregiver or self.caregiver,
            date=day,
            start_time=time.fromisoformat(start),
            end_time=time.fromisoformat(end),
        )

    def booking(self, start="10:00", end="11:00", day=DAY, status="accepted"):
        tz = timezone.get_current_timezone()
        return Booking.objects.create(
            owner=self.owner,
            pet=self.pet,
            caregiver=self.caregiver,
            service_type=self.walk,
            start_time=datetime.combine(day, time.fromisoformat(start), tz),
            end_time=datetime.combine(day, time.fromisoformat(end), tz),
            status=status,
        )

    def times(self):
        return [
            (s.start_time.strftime("%H:%M"), s.end_time.strftime("%H:%M"))
            for s in CaregiverAvailability.objects.filter(
                caregiver=self.caregiver
            ).order_by("date", "start_time")
        ]


class AvailabilityModelTests(AvailabilityTestData):
    def test_end_must_be_after_start(self):
        slot = CaregiverAvailability(
            caregiver=self.caregiver,
            date=DAY,
            start_time=time(12),
            end_time=time(9),
        )
        with self.assertRaisesMessage(ValidationError, "End time must be after"):
            slot.full_clean()

    def test_slots_cannot_overlap_but_can_touch(self):
        self.slot("09:00", "12:00")
        overlapping = CaregiverAvailability(
            caregiver=self.caregiver, date=DAY, start_time=time(11), end_time=time(13)
        )
        with self.assertRaisesMessage(ValidationError, "overlaps"):
            overlapping.full_clean()
        touching = CaregiverAvailability(
            caregiver=self.caregiver, date=DAY, start_time=time(12), end_time=time(13)
        )
        touching.full_clean()
        # Another caregiver's slots don't count.
        CaregiverAvailability(
            caregiver=self.other, date=DAY, start_time=time(10), end_time=time(11)
        ).full_clean()

    def test_str(self):
        self.assertEqual(
            str(self.slot("09:00", "12:00")), f"Chloe Shih: {DAY} 09:00:00–12:00:00"
        )


class ManageAvailabilityPageTests(AvailabilityTestData):
    def test_login_required(self):
        self.client.logout()
        response = self.client.get(MANAGE_URL)
        self.assertRedirects(response, f"{reverse('login')}?next={MANAGE_URL}")

    def test_only_caregivers_have_a_calendar(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(MANAGE_URL).status_code, 404)

    def test_shows_own_slots_and_bookings(self):
        self.slot("09:00", "12:00")
        self.slot("08:00", "09:00", caregiver=self.other)
        self.booking("10:00", "11:00")
        self.booking("13:00", "14:00", status="pending")  # not on the calendar
        response = self.client.get(MANAGE_URL)
        self.assertEqual(response.status_code, 200)
        slots = json.loads(response.context["calendar_slots"])
        bookings = json.loads(response.context["calendar_bookings"])
        self.assertEqual(
            [(s["date"], s["start"], s["end"]) for s in slots],
            [(DAY.isoformat(), "09:00", "12:00")],
        )
        self.assertEqual(
            [(b["start"], b["end"], b["status"], b["pet"]) for b in bookings],
            [("10:00", "11:00", "accepted", "Biscuit")],
        )

    def test_nav_links_to_the_calendar(self):
        response = self.client.get(reverse("bookings:caregiver_requests"))
        self.assertContains(response, f'href="{MANAGE_URL}"')

    def test_add_a_slot(self):
        response = self.client.post(
            MANAGE_URL, {"date": DAY, "start_time": "09:00", "end_time": "12:00"}
        )
        self.assertRedirects(response, MANAGE_URL)
        self.assertEqual(self.times(), [("09:00", "12:00")])

    def test_add_rejects_bad_or_overlapping_times(self):
        self.slot("09:00", "12:00")
        for start, end in (("13:00", "12:00"), ("11:00", "13:00")):
            response = self.client.post(
                MANAGE_URL, {"date": DAY, "start_time": start, "end_time": end}
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(self.times(), [("09:00", "12:00")])


class EditAndDeleteSlotTests(AvailabilityTestData):
    def test_edit_page_and_update(self):
        slot = self.slot("09:00", "12:00")
        url = reverse("edit_availability", args=[slot.pk])
        self.assertContains(self.client.get(url), "Edit Availability")
        response = self.client.post(
            url, {"date": DAY, "start_time": "13:00", "end_time": "15:00"}
        )
        self.assertRedirects(response, MANAGE_URL)
        self.assertEqual(self.times(), [("13:00", "15:00")])

    def test_edit_into_an_overlap_shows_an_error(self):
        self.slot("09:00", "12:00")
        slot = self.slot("13:00", "15:00")
        response = self.client.post(
            reverse("edit_availability", args=[slot.pk]),
            {"date": DAY, "start_time": "11:00", "end_time": "14:00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlaps with an existing time slot")
        self.assertEqual(self.times(), [("09:00", "12:00"), ("13:00", "15:00")])

    def test_delete_needs_post(self):
        slot = self.slot()
        url = reverse("delete_availability", args=[slot.pk])
        self.assertRedirects(self.client.get(url), MANAGE_URL)
        self.assertTrue(CaregiverAvailability.objects.filter(pk=slot.pk).exists())
        self.assertRedirects(self.client.post(url), MANAGE_URL)
        self.assertFalse(CaregiverAvailability.objects.filter(pk=slot.pk).exists())

    def test_cannot_touch_another_caregivers_slot(self):
        theirs = self.slot(caregiver=self.other)
        for name in ("edit_availability", "delete_availability"):
            response = self.client.post(reverse(name, args=[theirs.pk]))
            self.assertEqual(response.status_code, 404)
        self.assertTrue(CaregiverAvailability.objects.filter(pk=theirs.pk).exists())


class SaveAvailabilityChangesTests(AvailabilityTestData):
    def save(self, changes):
        return self.client.post(
            SAVE_URL, json.dumps({"changes": changes}), content_type="application/json"
        )

    def assert_rejected(self, changes, message):
        before = self.times()
        response = self.save(changes)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn(message, response.json()["error"])
        self.assertEqual(self.times(), before)

    def test_create_update_and_delete_in_one_save(self):
        keep = self.slot("08:00", "09:00")
        drop = self.slot("13:00", "14:00")
        response = self.save(
            [
                {
                    "action": "update",
                    "id": keep.pk,
                    "date": DAY.isoformat(),
                    "start": "07:00",
                    "end": "08:30",
                },
                {"action": "delete", "id": drop.pk},
                {
                    "action": "create",
                    "date": DAY.isoformat(),
                    "start": "10:00",
                    "end": "12:00",
                },
            ]
        )
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(self.times(), [("07:00", "08:30"), ("10:00", "12:00")])

    def test_moving_slots_is_checked_as_a_whole(self):
        # Swapping two slots' times is fine even though each step alone overlaps.
        a = self.slot("09:00", "10:00")
        b = self.slot("10:00", "11:00")
        response = self.save(
            [
                {
                    "action": "update",
                    "id": a.pk,
                    "date": DAY.isoformat(),
                    "start": "10:00",
                    "end": "11:00",
                },
                {
                    "action": "update",
                    "id": b.pk,
                    "date": DAY.isoformat(),
                    "start": "09:00",
                    "end": "10:00",
                },
            ]
        )
        self.assertEqual(response.json(), {"ok": True})

    def test_rejects_bad_requests(self):
        response = self.client.post(
            SAVE_URL, "not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assert_rejected([], "between 1 and 100")
        self.assert_rejected([{}] * 101, "between 1 and 100")
        self.assert_rejected(["x"], "must be an object")
        self.assert_rejected([{"action": "move"}], "Unknown availability action")

    def test_rejects_unknown_or_repeated_slots(self):
        mine = self.slot()
        theirs = self.slot(caregiver=self.other)
        self.assert_rejected([{"action": "delete", "id": theirs.pk}], "was not found")
        self.assert_rejected(
            [{"action": "delete", "id": str(mine.pk)}], "was not found"
        )
        self.assert_rejected(
            [{"action": "delete", "id": mine.pk}, {"action": "delete", "id": mine.pk}],
            "more than once",
        )

    def test_rejects_bad_times_and_overlaps(self):
        self.slot("09:00", "12:00")
        self.assert_rejected(
            [{"action": "create", "date": "someday", "start": "09:00", "end": "10:00"}],
            "valid date",
        )
        self.assert_rejected(
            [
                {
                    "action": "create",
                    "date": DAY.isoformat(),
                    "start": "15:00",
                    "end": "14:00",
                }
            ],
            "End time must be after start time",
        )
        self.assert_rejected(
            [
                {
                    "action": "create",
                    "date": DAY.isoformat(),
                    "start": "11:00",
                    "end": "13:00",
                }
            ],
            "cannot overlap",
        )

    def test_booked_time_cannot_be_changed_or_removed(self):
        slot = self.slot("09:00", "12:00")
        self.booking("10:00", "11:00", status="accepted")
        self.assert_rejected([{"action": "delete", "id": slot.pk}], "cannot be edited")
        self.assert_rejected(
            [
                {
                    "action": "update",
                    "id": slot.pk,
                    "date": DAY.isoformat(),
                    "start": "13:00",
                    "end": "15:00",
                }
            ],
            "cannot be edited",
        )

    def test_get_is_not_allowed_and_owners_have_no_calendar(self):
        self.assertEqual(self.client.get(SAVE_URL).status_code, 405)
        self.client.force_login(self.owner)
        response = self.save(
            [
                {
                    "action": "create",
                    "date": DAY.isoformat(),
                    "start": "09:00",
                    "end": "10:00",
                }
            ]
        )
        self.assertEqual(response.status_code, 404)


class PublicProfileCalendarTests(AvailabilityTestData):
    def public_slots(self):
        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        return [
            (s["date"], s["start"], s["end"])
            for s in json.loads(response.context["public_availability_json"])
        ]

    def test_owners_see_open_time_without_booked_time(self):
        self.slot("09:00", "17:00")
        self.booking("10:00", "11:00", status="accepted")
        self.booking("13:00", "14:00", status="completed")
        self.booking("15:00", "16:00", status="pending")  # still open
        self.client.force_login(self.owner)
        self.assertEqual(
            self.public_slots(),
            [
                (DAY.isoformat(), "09:00", "10:00"),
                (DAY.isoformat(), "11:00", "13:00"),
                (DAY.isoformat(), "14:00", "17:00"),
            ],
        )

    def test_overnight_booking_blocks_both_days(self):
        next_day = DAY + timedelta(days=1)
        self.slot("20:00", "23:59")
        self.slot("00:00", "10:00", day=next_day)
        tz = timezone.get_current_timezone()
        Booking.objects.create(
            owner=self.owner,
            pet=self.pet,
            caregiver=self.caregiver,
            service_type=self.walk,
            start_time=datetime.combine(DAY, time(22), tz),
            end_time=datetime.combine(next_day, time(8), tz),
            status="accepted",
        )
        self.client.force_login(self.owner)
        self.assertEqual(
            self.public_slots(),
            [
                (DAY.isoformat(), "20:00", "22:00"),
                (next_day.isoformat(), "08:00", "10:00"),
            ],
        )

    def test_fully_booked_slot_disappears(self):
        self.slot("10:00", "11:00")
        self.booking("10:00", "11:00", status="accepted")
        self.client.force_login(self.owner)
        self.assertEqual(self.public_slots(), [])
