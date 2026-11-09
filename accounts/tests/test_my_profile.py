"""#47 Update Personal Information: a pet owner's My profile and Edit profile
pages, the "…" menu with Delete account, and the caregiver's private
Personal info card (Kat's Figma)."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.deletion import delete_account
from accounts.models import AccountProfile
from caregivers.geocoding import GeocodingUnavailable, Location
from caregivers.models import CaregiverProfile
from pets.models import Pet, PetType

User = get_user_model()
PROFILE_URL = reverse("my_profile")
EDIT_URL = reverse("edit_profile")
DELETE_URL = reverse("delete_account")

PARK_SLOPE = Location(
    latitude=Decimal("40.672"),
    longitude=Decimal("-73.977"),
    neighborhood="Park Slope",
    borough="Brooklyn",
)


class MyProfileTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            "kat",
            email="kat@example.com",
            first_name="Kat",
            last_name="Wongsrisoontorn",
        )
        cls.profile = AccountProfile.objects.create(
            user=cls.owner,
            address="215 6th Ave, Brooklyn",
            neighborhood="Park Slope, Brooklyn",
        )
        dog = PetType.objects.get_or_create(name="Dog")[0]
        Pet.objects.create(owner=cls.owner, name="Miso", pet_type=dog)
        Pet.objects.create(owner=cls.owner, name="Tofu", pet_type=dog)
        Pet.objects.create(
            owner=cls.owner, name="Old", pet_type=dog, deleted_at=timezone.now()
        )

        cls.sitter = User.objects.create_user("chloe", email="chloe@example.com")
        AccountProfile.objects.create(
            user=cls.sitter, role=AccountProfile.Role.CAREGIVER
        )
        cls.caregiver = CaregiverProfile.objects.create(
            user=cls.sitter,
            name="Chloe Shih",
            service_area="Park Slope, Brooklyn",
            address="421 7th Ave, Brooklyn",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def save(self, **overrides):
        data = {
            "first_name": "Kat",
            "last_name": "Wongsrisoontorn",
            "email": "kat@example.com",
            "address": "215 6th Ave, Brooklyn",
        }
        data.update(overrides)
        return self.client.post(EDIT_URL, data, follow=True)


class AccountMenuTests(MyProfileTestData):
    def test_owner_menu_has_my_profile_and_log_out_only(self):
        response = self.client.get(reverse("pets:list"))
        self.assertContains(response, f'href="{PROFILE_URL}"')
        self.assertContains(response, "Log out")
        self.assertNotContains(response, f'href="{DELETE_URL}"')
        self.assertNotContains(response, "Your neighborhood")

    def test_caregiver_menu_has_no_delete_account(self):
        self.client.force_login(self.sitter)
        response = self.client.get(reverse("bookings:caregiver_requests"))
        self.assertNotContains(response, f'href="{DELETE_URL}"')


class MyProfilePageTests(MyProfileTestData):
    def test_shows_the_header_and_personal_info(self):
        response = self.client.get(PROFILE_URL)
        self.assertContains(response, "<h1>Kat W.</h1>", html=True)
        self.assertContains(response, "Park Slope, Brooklyn")
        self.assertContains(response, "2 pets")  # The deleted pet isn't counted.
        self.assertContains(response, "Personal info")
        for value in ("Kat", "Wongsrisoontorn", "kat@example.com", "215 6th Ave"):
            self.assertContains(response, value)
        self.assertContains(response, f'href="{EDIT_URL}"')
        self.assertContains(response, f'href="{DELETE_URL}"')

    def test_missing_details_say_not_added_yet(self):
        owner = User.objects.create_user("sam")
        self.client.force_login(owner)
        response = self.client.get(PROFILE_URL)
        self.assertContains(response, "<h1>sam</h1>", html=True)
        self.assertContains(response, "0 pets")
        self.assertContains(response, "Not added yet", count=4)
        # The profile is made if the account didn't have one yet.
        self.assertTrue(AccountProfile.objects.filter(user=owner).exists())

    def test_login_is_required(self):
        self.client.logout()
        for url in (PROFILE_URL, EDIT_URL):
            self.assertRedirects(
                self.client.get(url),
                f"{reverse('login')}?next={url}",
                fetch_redirect_response=False,
            )

    def test_caregiver_goes_to_their_caregiver_profile(self):
        self.client.force_login(self.sitter)
        for url in (PROFILE_URL, EDIT_URL):
            self.assertRedirects(
                self.client.get(url),
                reverse("caregiver", args=[self.caregiver.pk]),
                fetch_redirect_response=False,
            )

    def test_caregiver_without_a_profile_goes_to_make_one(self):
        newbie = User.objects.create_user("nina")
        AccountProfile.objects.create(user=newbie, role=AccountProfile.Role.CAREGIVER)
        self.client.force_login(newbie)
        self.assertRedirects(
            self.client.get(PROFILE_URL),
            reverse("create_caregiver_profile"),
            fetch_redirect_response=False,
        )

    def test_admin_goes_home(self):
        admin = User.objects.create_user("ada", is_staff=True)
        self.client.force_login(admin)
        self.assertRedirects(
            self.client.get(EDIT_URL), reverse("home"), fetch_redirect_response=False
        )


class EditProfileTests(MyProfileTestData):
    def test_form_is_filled_in(self):
        response = self.client.get(EDIT_URL)
        self.assertContains(response, "Edit your profile")
        self.assertContains(response, 'value="Wongsrisoontorn"')
        self.assertContains(response, 'value="kat@example.com"')
        self.assertContains(response, 'value="215 6th Ave, Brooklyn"')
        self.assertContains(response, "Only you can see email &amp; address")

    @mock.patch("accounts.forms.geocode", return_value=PARK_SLOPE)
    def test_saves_name_and_new_address(self, geocode):
        response = self.save(
            first_name=" Katherine ", last_name="W", address="200 5th Ave"
        )
        self.assertRedirects(response, PROFILE_URL)
        self.assertContains(response, "Your profile is saved.")
        geocode.assert_called_once_with("200 5th Ave")
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(
            (self.owner.first_name, self.owner.last_name), ("Katherine", "W")
        )
        self.assertEqual(self.profile.address, "200 5th Ave")
        self.assertEqual(self.profile.neighborhood, "Park Slope, Brooklyn")

    @mock.patch("accounts.forms.geocode")
    def test_same_address_is_not_looked_up_again(self, geocode):
        self.save(first_name="Kathy")
        geocode.assert_not_called()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.neighborhood, "Park Slope, Brooklyn")

    @mock.patch("accounts.forms.geocode", return_value=None)
    def test_address_outside_nyc_is_rejected(self, geocode):
        response = self.save(first_name="Kathy", address="1 Main St, Boston")
        self.assertContains(response, "We couldn&#x27;t find this address")
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.owner.first_name, "Kat")
        self.assertEqual(self.profile.address, "215 6th Ave, Brooklyn")

    @mock.patch("accounts.forms.geocode", side_effect=GeocodingUnavailable("down"))
    def test_saves_without_a_neighborhood_when_lookup_is_down(self, geocode):
        response = self.save(address="200 5th Ave")
        self.assertContains(response, "couldn&#x27;t look up your neighborhood")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.address, "200 5th Ave")
        self.assertEqual(self.profile.neighborhood, "")

    def test_required_fields(self):
        response = self.save(first_name=" ", last_name="", address="")
        self.assertContains(response, "Enter your first name.")
        self.assertContains(response, "Enter your last name.")
        self.assertContains(response, "Enter your address.")
        response = self.save(email="")
        self.assertContains(response, "Enter your email.")

    def test_cancel_goes_back_to_my_profile(self):
        self.assertContains(self.client.get(EDIT_URL), f'href="{PROFILE_URL}"')


class CaregiverPersonalInfoTests(MyProfileTestData):
    def test_caregiver_sees_their_private_info_and_more_menu(self):
        self.client.force_login(self.sitter)
        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertContains(response, "Only you can see this")
        self.assertContains(response, "chloe@example.com")
        self.assertContains(response, "421 7th Ave, Brooklyn")
        self.assertContains(response, "More options")
        self.assertContains(response, f'href="{DELETE_URL}"')

    def test_owners_viewing_the_profile_dont_see_it(self):
        response = self.client.get(reverse("caregiver", args=[self.caregiver.pk]))
        self.assertNotContains(response, "Only you can see this")
        self.assertNotContains(response, "chloe@example.com")
        self.assertNotContains(response, "421 7th Ave")
        self.assertNotContains(response, f'href="{DELETE_URL}"')


class DeletingTests(MyProfileTestData):
    def test_deleting_the_account_clears_the_address_and_neighborhood(self):
        delete_account(self.owner)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.address, self.profile.neighborhood), ("", ""))
