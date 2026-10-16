from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.models import CaregiverProfile, ServiceType
from pets.models import Pet, PetType

from .forms import BookingRequestForm
from .models import Booking

FMT = "%Y-%m-%dT%H:%M"


class BookingTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        dog = PetType.objects.create(name="Dog")
        cls.pet = Pet.objects.create(name="Biscuit", pet_type=dog)
        cls.caregiver = CaregiverProfile.objects.create(
            name="Jamie", service_area="Brooklyn"
        )
        cls.walk = ServiceType.objects.create(name="Dog Walking")
        cls.sitting = ServiceType.objects.create(name="Pet Sitting")

    def form_data(self, **overrides):
        start = timezone.now() + timedelta(days=2)
        data = {
            "pet": self.pet.pk,
            "caregiver": self.caregiver.pk,
            "service_type": self.walk.pk,
            "start_time": start.strftime(FMT),
            "end_time": (start + timedelta(hours=1)).strftime(FMT),
            "notes": "Please bring treats.",
        }
        data.update(overrides)
        return data

    def make_booking(self, owner=None, **fields):
        start = timezone.now() + timedelta(days=1)
        defaults = {
            "owner": owner,
            "pet": self.pet,
            "caregiver": self.caregiver,
            "service_type": self.walk,
            "start_time": start,
            "end_time": start + timedelta(hours=1),
        }
        defaults.update(fields)
        return Booking.objects.create(**defaults)


class BookingModelTests(BookingTestData):
    def test_new_booking_defaults_to_pending(self):
        booking = self.make_booking()
        self.assertEqual(booking.status, Booking.Status.PENDING)


class BookingRequestFormTests(BookingTestData):
    def test_valid_request(self):
        self.assertTrue(BookingRequestForm(data=self.form_data()).is_valid())

    def test_pet_caregiver_and_service_are_required(self):
        form = BookingRequestForm(
            data=self.form_data(pet="", caregiver="", service_type="")
        )
        self.assertFalse(form.is_valid())
        for field in ("pet", "caregiver", "service_type"):
            self.assertIn(field, form.errors)

    def test_start_time_must_be_in_future(self):
        past = timezone.now() - timedelta(days=1)
        form = BookingRequestForm(
            data=self.form_data(
                start_time=past.strftime(FMT),
                end_time=(past + timedelta(hours=1)).strftime(FMT),
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("start_time", form.errors)

    def test_end_time_must_be_after_start(self):
        data = self.form_data()
        data["end_time"] = data["start_time"]
        form = BookingRequestForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("end_time", form.errors)

    def test_caregiver_not_accepting_bookings_cannot_be_selected(self):
        self.caregiver.accepting_new_bookings = False
        self.caregiver.save()
        form = BookingRequestForm(data=self.form_data())
        self.assertFalse(form.is_valid())
        self.assertIn("caregiver", form.errors)

    def test_service_must_be_offered_by_caregiver(self):
        with mock.patch(
            "bookings.forms.offered_service_type_ids", return_value={self.sitting.pk}
        ):
            form = BookingRequestForm(data=self.form_data())
            self.assertFalse(form.is_valid())
            self.assertIn("service_type", form.errors)

    def test_service_accepted_when_offered_by_caregiver(self):
        with mock.patch(
            "bookings.forms.offered_service_type_ids", return_value={self.walk.pk}
        ):
            self.assertTrue(BookingRequestForm(data=self.form_data()).is_valid())


class BookingCreateViewTests(BookingTestData):
    def test_get_shows_form(self):
        response = self.client.get(reverse("bookings:booking_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request Care")
        self.assertContains(response, "Biscuit")
        self.assertContains(response, "Jamie")

    def test_caregiver_can_be_preselected(self):
        response = self.client.get(
            reverse("bookings:booking_create"), {"caregiver": self.caregiver.pk}
        )
        self.assertEqual(
            response.context["form"].initial["caregiver"], str(self.caregiver.pk)
        )

    def test_post_saves_pending_booking_and_shows_it(self):
        response = self.client.post(
            reverse("bookings:booking_create"), self.form_data(), follow=True
        )
        booking = Booking.objects.get()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.pet, self.pet)
        self.assertEqual(booking.caregiver, self.caregiver)
        self.assertEqual(booking.service_type, self.walk)
        self.assertRedirects(
            response, reverse("bookings:booking_detail", args=[booking.pk])
        )
        self.assertContains(response, "Pending")

    def test_post_by_signed_in_user_sets_owner(self):
        user = get_user_model().objects.create_user("owner", password="pw-12345!")
        self.client.force_login(user)
        self.client.post(reverse("bookings:booking_create"), self.form_data())
        self.assertEqual(Booking.objects.get().owner, user)

    def test_invalid_post_saves_nothing(self):
        response = self.client.post(
            reverse("bookings:booking_create"), self.form_data(pet="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.exists())


class BookingListAndDetailViewTests(BookingTestData):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user("alice", password="pw-12345!")
        self.bob = User.objects.create_user("bob", password="pw-12345!")

    def test_empty_list(self):
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, "You have not requested any bookings yet.")

    def test_list_shows_submitted_booking(self):
        self.make_booking()
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, "Biscuit")
        self.assertContains(response, "Jamie")
        self.assertContains(response, "Dog Walking")
        self.assertContains(response, "Pending")

    def test_signed_in_owner_sees_only_their_bookings(self):
        self.make_booking(owner=self.alice, notes="alice")
        bob_booking = self.make_booking(owner=self.bob, service_type=self.sitting)
        self.client.force_login(self.alice)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertEqual(len(response.context["bookings"]), 1)
        self.assertNotContains(response, "Pet Sitting")
        detail = self.client.get(
            reverse("bookings:booking_detail", args=[bob_booking.pk])
        )
        self.assertEqual(detail.status_code, 404)

    def test_anonymous_visitor_cannot_see_owned_bookings(self):
        booking = self.make_booking(owner=self.alice)
        response = self.client.get(
            reverse("bookings:booking_detail", args=[booking.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_request_details(self):
        booking = self.make_booking(notes="Feed at 6pm")
        response = self.client.get(
            reverse("bookings:booking_detail", args=[booking.pk])
        )
        self.assertContains(response, "Feed at 6pm")
        self.assertContains(response, "Pending")
