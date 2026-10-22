from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.geocoding import Location
from caregivers.models import CaregiverProfile, ServiceType
from pets.models import Pet, PetType

from .forms import BookingRequestForm
from .models import Booking

FMT = "%Y-%m-%dT%H:%M"


class BookingTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("owner", password="pw-12345!")
        cls.other_owner = User.objects.create_user("other", password="pw-12345!")
        dog = PetType.objects.get_or_create(name="Dog")[0]
        cls.pet = Pet.objects.create(owner=cls.owner, name="Biscuit", pet_type=dog)
        cls.other_pet = Pet.objects.create(
            owner=cls.other_owner, name="Rex", pet_type=dog
        )
        cls.caregiver = CaregiverProfile.objects.create(
            name="Chloe Shih", service_area="Brooklyn"
        )
        # Created by the 0002 data migration.
        cls.walk = ServiceType.objects.get(name="Dog walking")
        cls.sitting = ServiceType.objects.get(name="Pet sitting")

    def form_data(self, **overrides):
        start = timezone.localtime() + timedelta(days=2)
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

    def make_booking(self, owner=None, pet=None, **fields):
        start = timezone.now() + timedelta(days=1)
        defaults = {
            "owner": owner or self.owner,
            "pet": pet or self.pet,
            "caregiver": self.caregiver,
            "service_type": self.walk,
            "start_time": start,
            "end_time": start + timedelta(hours=1),
        }
        defaults.update(fields)
        return Booking.objects.create(**defaults)


class BookingModelTests(BookingTestData):
    def test_new_booking_defaults_to_pending(self):
        self.assertEqual(self.make_booking().status, Booking.Status.PENDING)

    def test_default_service_types_exist(self):
        names = set(ServiceType.objects.values_list("name", flat=True))
        self.assertTrue({"Dog walking", "Pet sitting", "Drop-in visit"} <= names)


class BookingRequestFormTests(BookingTestData):
    def make_form(self, **overrides):
        return BookingRequestForm(data=self.form_data(**overrides), owner=self.owner)

    def test_valid_request(self):
        self.assertTrue(self.make_form().is_valid())

    def test_only_owners_pets_are_offered(self):
        form = BookingRequestForm(owner=self.owner)
        self.assertEqual(list(form.fields["pet"].queryset), [self.pet])

    def test_cannot_book_someone_elses_pet(self):
        form = self.make_form(pet=self.other_pet.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("pet", form.errors)

    def test_pet_caregiver_service_and_times_are_required(self):
        form = self.make_form(
            pet="", caregiver="", service_type="", start_time="", end_time=""
        )
        self.assertFalse(form.is_valid())
        for field in ("pet", "caregiver", "service_type", "start_time", "end_time"):
            self.assertIn(field, form.errors)

    def test_start_time_must_be_in_future(self):
        past = timezone.localtime() - timedelta(hours=1)
        form = self.make_form(
            start_time=past.strftime(FMT),
            end_time=(past + timedelta(hours=2)).strftime(FMT),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("start_time", form.errors)

    def test_times_are_entered_in_local_time(self):
        # A time later today in New York must be accepted (not read as UTC).
        soon = timezone.localtime() + timedelta(minutes=30)
        form = self.make_form(
            start_time=soon.strftime(FMT),
            end_time=(soon + timedelta(hours=1)).strftime(FMT),
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_end_time_must_be_after_start(self):
        data = self.form_data()
        form = self.make_form(end_time=data["start_time"])
        self.assertFalse(form.is_valid())
        self.assertIn("end_time", form.errors)

    def test_caregiver_not_accepting_bookings_cannot_be_selected(self):
        self.caregiver.accepting_new_bookings = False
        self.caregiver.save()
        form = self.make_form()
        self.assertFalse(form.is_valid())
        self.assertIn("caregiver", form.errors)

    def test_service_must_be_offered_by_caregiver(self):
        with mock.patch(
            "bookings.forms.offered_service_type_ids", return_value={self.sitting.pk}
        ):
            form = self.make_form()
            self.assertFalse(form.is_valid())
            self.assertIn("service_type", form.errors)

    def test_service_accepted_when_offered_by_caregiver(self):
        with mock.patch(
            "bookings.forms.offered_service_type_ids", return_value={self.walk.pk}
        ):
            self.assertTrue(self.make_form().is_valid())


class BookingCreateViewTests(BookingTestData):
    url = reverse("bookings:booking_create")

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_get_shows_form_with_own_pets_only(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, "Request care")
        self.assertContains(response, "Biscuit")
        self.assertContains(response, "Chloe Shih")
        self.assertContains(response, "Dog walking")
        self.assertNotContains(response, "Rex")

    def test_owner_without_pets_is_asked_to_add_one(self):
        self.client.force_login(get_user_model().objects.create_user("new"))
        response = self.client.get(self.url)
        self.assertContains(response, "Add a pet first")

    def test_caregiver_and_pet_can_be_preselected(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            self.url, {"caregiver": self.caregiver.pk, "pet": self.pet.pk}
        )
        initial = response.context["form"].initial
        self.assertEqual(initial["caregiver"], str(self.caregiver.pk))
        self.assertEqual(initial["pet"], str(self.pet.pk))

    def test_post_saves_pending_booking_and_confirms(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, self.form_data(), follow=True)
        booking = Booking.objects.get()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.owner, self.owner)
        self.assertEqual(booking.pet, self.pet)
        self.assertEqual(booking.caregiver, self.caregiver)
        self.assertEqual(booking.service_type, self.walk)
        self.assertRedirects(response, booking.get_absolute_url())
        self.assertContains(response, "Request sent to Chloe Shih")
        self.assertContains(response, "Pending")

    def test_invalid_post_saves_nothing(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, self.form_data(pet=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose one of your pets.")
        self.assertFalse(Booking.objects.exists())


class BookingListAndDetailViewTests(BookingTestData):
    def test_list_login_required(self):
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertEqual(response.status_code, 302)

    def test_empty_list(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, "No requests yet")

    def test_list_shows_submitted_booking(self):
        self.make_booking()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, "Biscuit · Dog walking")
        self.assertContains(response, "Chloe Shih")
        self.assertContains(response, "Pending")

    def test_owner_sees_only_their_bookings(self):
        self.make_booking()
        other = self.make_booking(owner=self.other_owner, pet=self.other_pet)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertEqual(len(response.context["active"]) + len(response.context["history"]), 1)
        self.assertNotContains(response, "Rex")
        detail = self.client.get(other.get_absolute_url())
        self.assertEqual(detail.status_code, 404)

    def test_detail_shows_request_details(self):
        booking = self.make_booking(notes="Feed at 6pm")
        self.client.force_login(self.owner)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Feed at 6pm")
        self.assertContains(response, "Pending")
        self.assertContains(response, "Chloe Shih")


class BookingPanelTests(BookingTestData):
    def test_my_pets_page_shows_latest_requests(self):
        self.make_booking()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("pets:list"))
        self.assertContains(response, "My booking requests")
        self.assertContains(response, "Biscuit · Dog walking")
        self.assertContains(response, reverse("bookings:booking_create"))

    def test_nav_links_to_my_requests(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("pets:list"))
        self.assertContains(response, f'href="{reverse("bookings:booking_list")}"')


class CaregiverTestData(BookingTestData):
    """Adds a signed-in caregiver who owns the caregiver profile."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        User = get_user_model()
        cls.sitter = User.objects.create_user(
            "chloe", password="pw-12345!", first_name="Chloe", last_name="Shih"
        )
        cls.caregiver.user = cls.sitter
        cls.caregiver.save()
        cls.other_sitter = User.objects.create_user("sam", password="pw-12345!")
        cls.other_caregiver = CaregiverProfile.objects.create(
            name="Sam Lee", service_area="Queens", user=cls.other_sitter
        )

    def respond(self, booking, action):
        return self.client.post(
            reverse("bookings:booking_respond", args=[booking.pk]),
            {"action": action},
        )


class IncomingRequestsViewTests(CaregiverTestData):
    url = reverse("bookings:caregiver_requests")

    def booking_at(self, days, **fields):
        start = timezone.now() + timedelta(days=days)
        return self.make_booking(
            start_time=start, end_time=start + timedelta(hours=1), **fields
        )

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_user_without_profile_is_asked_to_create_one(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, "Create your caregiver profile first")

    def test_caregiver_sees_only_their_requests(self):
        mine = self.make_booking()
        theirs = self.make_booking(caregiver=self.other_caregiver)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url)
        self.assertIn(mine, response.context["bookings"])
        self.assertNotIn(theirs, response.context["bookings"])

    def test_pending_tab_is_default_and_soonest_first(self):
        later = self.booking_at(3)
        sooner = self.booking_at(1)
        self.booking_at(2, status=Booking.Status.ACCEPTED)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url)
        self.assertEqual(response.context["active_tab"], "pending")
        self.assertEqual(response.context["bookings"], [sooner, later])
        self.assertContains(response, "2 requests need your response.")

    def test_tab_counts(self):
        self.booking_at(1)
        self.booking_at(2, status=Booking.Status.ACCEPTED)
        self.booking_at(3, status=Booking.Status.DECLINED)
        self.client.force_login(self.sitter)
        counts = {
            tab["key"]: tab["count"]
            for tab in self.client.get(self.url).context["tabs"]
        }
        self.assertEqual(
            counts, {"pending": 1, "accepted": 1, "declined": 1, "all": 3}
        )

    def test_accepted_and_declined_tabs(self):
        self.booking_at(1)
        accepted = self.booking_at(2, status=Booking.Status.ACCEPTED)
        declined = self.booking_at(3, status=Booking.Status.DECLINED)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url, {"status": "accepted"})
        self.assertEqual(response.context["bookings"], [accepted])
        response = self.client.get(self.url, {"status": "declined"})
        self.assertEqual(response.context["bookings"], [declined])

    def test_unknown_tab_falls_back_to_pending(self):
        self.client.force_login(self.sitter)
        response = self.client.get(self.url, {"status": "nonsense"})
        self.assertEqual(response.context["active_tab"], "pending")

    def test_first_request_is_selected_by_default(self):
        first = self.booking_at(1)
        self.booking_at(2)
        self.client.force_login(self.sitter)
        self.assertEqual(self.client.get(self.url).context["selected"], first)

    def test_request_can_be_selected(self):
        self.booking_at(1)
        second = self.booking_at(2)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url, {"b": second.pk})
        self.assertEqual(response.context["selected"], second)

    def test_cannot_select_another_caregivers_request(self):
        mine = self.booking_at(1)
        theirs = self.booking_at(2, caregiver=self.other_caregiver)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url, {"b": theirs.pk})
        self.assertEqual(response.context["selected"], mine)

    def test_panel_shows_pet_owner_care_needs_and_note(self):
        self.owner.first_name, self.owner.last_name = "Kat", "Wong"
        self.owner.save()
        self.pet.special_care_instructions = "Pulls on the leash near squirrels."
        self.pet.save()
        self.booking_at(1, notes="Treats are in the jar.")
        self.client.force_login(self.sitter)
        response = self.client.get(self.url)
        self.assertContains(response, "Owner: Kat W.")
        self.assertContains(response, "Pulls on the leash near squirrels.")
        self.assertContains(response, "Note from Kat")
        self.assertContains(response, "Treats are in the jar.")
        self.assertContains(response, ">Accept</button>")

    def test_no_buttons_for_answered_request(self):
        self.booking_at(1, status=Booking.Status.ACCEPTED)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url, {"status": "accepted"})
        self.assertNotContains(response, ">Accept</button>")

    def test_upcoming_care_lists_future_accepted_bookings(self):
        accepted = self.booking_at(2, status=Booking.Status.ACCEPTED)
        self.booking_at(1)
        self.client.force_login(self.sitter)
        response = self.client.get(self.url)
        self.assertEqual(list(response.context["upcoming"]), [accepted])
        self.assertContains(response, "Upcoming care")

    def test_caregiver_nav(self):
        self.client.force_login(self.sitter)
        response = self.client.get(self.url)
        self.assertContains(response, ">Requests</a>")
        self.assertContains(response, ">My profile</a>")
        self.assertContains(response, "Caregiver")
        self.assertNotContains(response, ">My pets</a>")

    def test_owner_nav_unchanged(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, ">My pets</a>")
        self.assertNotContains(response, ">My profile</a>")


class CaregiverDetailViewTests(CaregiverTestData):
    def test_caregiver_sees_pet_details_and_buttons(self):
        self.pet.special_care_instructions = "Twice-daily insulin."
        self.pet.save()
        booking = self.make_booking()
        self.client.force_login(self.sitter)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Twice-daily insulin.")
        self.assertContains(response, "Accept request")
        self.assertContains(response, "Decline")

    def test_other_caregiver_cannot_see_request(self):
        booking = self.make_booking()
        self.client.force_login(self.other_sitter)
        response = self.client.get(booking.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_owner_does_not_see_respond_buttons(self):
        booking = self.make_booking()
        self.client.force_login(self.owner)
        self.assertNotContains(
            self.client.get(booking.get_absolute_url()), "Accept request"
        )


class RespondToRequestTests(CaregiverTestData):
    def setUp(self):
        self.client.force_login(self.sitter)

    def test_accept_pending_request(self):
        booking = self.make_booking()
        response = self.respond(booking, "accept")
        self.assertRedirects(response, booking.get_absolute_url())
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ACCEPTED)

    def test_decline_pending_request(self):
        booking = self.make_booking()
        self.respond(booking, "decline")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.DECLINED)

    def test_get_not_allowed(self):
        booking = self.make_booking()
        url = reverse("bookings:booking_respond", args=[booking.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_unknown_action_rejected(self):
        booking = self.make_booking()
        self.assertEqual(self.respond(booking, "maybe").status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_cannot_change_an_answered_request(self):
        booking = self.make_booking(status=Booking.Status.DECLINED)
        self.respond(booking, "accept")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.DECLINED)

    def test_cannot_respond_after_start_time(self):
        start = timezone.now() - timedelta(hours=1)
        booking = self.make_booking(start_time=start, end_time=start + timedelta(hours=2))
        self.respond(booking, "accept")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_other_caregiver_cannot_respond(self):
        booking = self.make_booking()
        self.client.force_login(self.other_sitter)
        self.assertEqual(self.respond(booking, "accept").status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_owner_cannot_respond_to_own_request(self):
        booking = self.make_booking()
        self.client.force_login(self.owner)
        self.assertEqual(self.respond(booking, "accept").status_code, 404)

    def test_overlapping_accept_is_refused(self):
        start = timezone.now() + timedelta(days=1)
        self.make_booking(
            status=Booking.Status.ACCEPTED,
            start_time=start,
            end_time=start + timedelta(hours=2),
        )
        clash = self.make_booking(
            start_time=start + timedelta(hours=1),
            end_time=start + timedelta(hours=3),
        )
        self.respond(clash, "accept")
        clash.refresh_from_db()
        self.assertEqual(clash.status, Booking.Status.PENDING)

    def test_back_to_back_bookings_can_both_be_accepted(self):
        start = timezone.now() + timedelta(days=1)
        self.make_booking(
            status=Booking.Status.ACCEPTED,
            start_time=start,
            end_time=start + timedelta(hours=1),
        )
        nxt = self.make_booking(
            start_time=start + timedelta(hours=1),
            end_time=start + timedelta(hours=2),
        )
        self.respond(nxt, "accept")
        nxt.refresh_from_db()
        self.assertEqual(nxt.status, Booking.Status.ACCEPTED)

    def test_returns_to_requests_page(self):
        booking = self.make_booking()
        back = reverse("bookings:caregiver_requests") + "?status=pending"
        response = self.client.post(
            reverse("bookings:booking_respond", args=[booking.pk]),
            {"action": "accept", "next": back},
        )
        self.assertRedirects(response, back)

    def test_ignores_outside_redirect(self):
        booking = self.make_booking()
        response = self.client.post(
            reverse("bookings:booking_respond", args=[booking.pk]),
            {"action": "accept", "next": "https://evil.example.com/"},
        )
        self.assertRedirects(response, booking.get_absolute_url())

    def test_accept_confirmation_has_details(self):
        self.owner.first_name, self.owner.last_name = "Kat", "Wong"
        self.owner.save()
        booking = self.make_booking()
        response = self.respond(booking, "accept")
        message = str(list(response.wsgi_request._messages)[0])
        self.assertIn("Request accepted: Biscuit · Dog walking on", message)
        self.assertIn("Kat W. will see it as Accepted", message)

    def test_decline_confirmation_has_details(self):
        booking = self.make_booking()
        response = self.respond(booking, "decline")
        message = str(list(response.wsgi_request._messages)[0])
        self.assertIn("Request declined: Biscuit · Dog walking on", message)
        self.assertIn("will see it as Declined", message)

    def test_owner_sees_accepted_note(self):
        booking = self.make_booking()
        self.respond(booking, "accept")
        self.client.force_login(self.owner)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Request accepted.")
        self.assertContains(response, "Chloe Shih accepted on")

    def test_owner_sees_declined_note_and_can_rebook(self):
        booking = self.make_booking()
        self.respond(booking, "decline")
        self.client.force_login(self.owner)
        response = self.client.get(booking.get_absolute_url())
        self.assertContains(response, "Request declined.")
        self.assertContains(response, "Request another caregiver")

    def test_owner_sees_new_status(self):
        booking = self.make_booking()
        self.respond(booking, "accept")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertContains(response, "Accepted")


class CaregiverProfileOwnershipTests(TestCase):
    # The profile form looks up the address; never call the real service here.
    @mock.patch("caregivers.forms.geocode")
    def test_new_profile_is_linked_to_signed_in_user(self, geocode):
        geocode.return_value = Location(
            latitude=Decimal("40.837"), longitude=Decimal("-73.866"),
            neighborhood="Parkchester", borough="Bronx",
        )
        user = get_user_model().objects.create_user("new", password="pw-12345!")
        self.client.force_login(user)
        response = self.client.post(
            reverse("create_caregiver_profile"),
            {
                "name": "Ana",
                "service_area": "Bronx",
                "years_of_experience": 2,
                "address": "1500 Unionport Rd, Bronx",
                "service_radius_miles": 3,
            },
        )
        profile = CaregiverProfile.objects.get(name="Ana")
        self.assertEqual(profile.user, user)
        self.assertRedirects(
            response, reverse("caregiver", args=[profile.pk]), fetch_redirect_response=False
        )


class CaregiverCannotRequestCareTests(CaregiverTestData):
    def test_caregiver_is_sent_to_their_requests(self):
        self.client.force_login(self.sitter)
        response = self.client.get(reverse("bookings:booking_create"))
        self.assertRedirects(response, reverse("bookings:caregiver_requests"))

    def test_caregiver_cannot_post_a_request(self):
        Pet.objects.create(owner=self.sitter, name="Deez", pet_type=self.pet.pet_type)
        self.client.force_login(self.sitter)
        self.client.post(reverse("bookings:booking_create"), self.form_data())
        self.assertFalse(Booking.objects.filter(owner=self.sitter).exists())

    def test_own_profile_not_offered(self):
        form = BookingRequestForm(owner=self.sitter)
        self.assertNotIn(self.caregiver, form.fields["caregiver"].queryset)
        self.assertIn(self.other_caregiver, form.fields["caregiver"].queryset)
