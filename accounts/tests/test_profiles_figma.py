"""Details from Kat's "PawPal - Profiles" Figma frames: the owner's profile
photo, the caregiver's "Accepting new requests" switch, and the caregiver
form's Cancel button."""

import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from accounts.tests.test_delete_account import PNG
from caregivers.models import CaregiverProfile
from pets.models import PetType

from .test_my_profile import EDIT_URL, PROFILE_URL, MyProfileTestData

MEDIA = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
@mock.patch("accounts.forms.geocode", return_value=None)
class OwnerPhotoTests(MyProfileTestData):
    def post(self, **files):
        data = {
            "first_name": "Kat",
            "last_name": "Wongsrisoontorn",
            "email": "kat@example.com",
            "address": "215 6th Ave, Brooklyn",
            **files,
        }
        return self.client.post(EDIT_URL, data, follow=True)

    def test_edit_page_has_the_photo_upload(self, geocode):
        response = self.client.get(EDIT_URL)
        self.assertContains(response, "Profile photo")
        self.assertContains(response, "Upload photo")
        self.assertContains(response, 'enctype="multipart/form-data"')
        # Figma has no helper lines under Email and Address.
        self.assertNotContains(response, "we'll email a link")
        self.assertNotContains(response, "Caregivers only see your neighborhood.")

    def test_uploaded_photo_shows_on_my_profile(self, geocode):
        photo = SimpleUploadedFile("me.png", PNG, content_type="image/png")
        response = self.post(photo=photo)
        self.assertRedirects(response, PROFILE_URL)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo.name.startswith("accounts/photos/"))
        self.assertContains(response, self.profile.photo.url)

    def test_photo_is_optional(self, geocode):
        response = self.post()
        self.assertRedirects(response, PROFILE_URL)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.photo)

    def test_big_or_broken_photos_are_rejected(self, geocode):
        with mock.patch("accounts.forms.MAX_PHOTO_MB", 0):
            photo = SimpleUploadedFile("me.png", PNG, content_type="image/png")
            response = self.post(photo=photo)
        self.assertContains(response, "Photo must be smaller than 0 MB.")
        broken = SimpleUploadedFile("me.png", b"not a png", content_type="image/png")
        response = self.post(photo=broken)
        self.assertContains(response, "Upload a JPG or PNG photo.")

    def test_new_photo_replaces_the_old_one(self, geocode):
        self.post(photo=SimpleUploadedFile("a.png", PNG, content_type="image/png"))
        self.profile.refresh_from_db()
        first = self.profile.photo.name
        self.post(photo=SimpleUploadedFile("b.png", PNG, content_type="image/png"))
        self.profile.refresh_from_db()
        self.assertNotEqual(self.profile.photo.name, first)


class CaregiverProfileFigmaTests(MyProfileTestData):
    def setUp(self):
        self.client.force_login(self.sitter)
        self.url = reverse("caregiver", args=[self.caregiver.pk])
        self.switch = reverse("set_accepting_requests", args=[self.caregiver.pk])

    def test_accepting_switch_turns_off_and_on(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Accepting new requests")
        self.assertContains(response, 'aria-checked="true"')
        response = self.client.post(self.switch, {"accepting": "0"})
        self.assertRedirects(response, self.url)
        self.caregiver.refresh_from_db()
        self.assertFalse(self.caregiver.accepting_new_bookings)
        self.client.post(self.switch, {"accepting": "1"})
        self.caregiver.refresh_from_db()
        self.assertTrue(self.caregiver.accepting_new_bookings)

    def test_only_the_caregiver_can_flip_it(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.switch, {"accepting": "0"})
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(self.client.get(self.url), "Accepting new requests")
        self.assertEqual(self.client.get(self.switch).status_code, 405)

    def test_pet_tags_are_plural_with_dogs_first(self):
        cat = PetType.objects.get_or_create(name="Cat")[0]
        dog = PetType.objects.get_or_create(name="Dog")[0]
        self.caregiver.supported_pet_types.set([cat, dog])
        response = self.client.get(self.url)
        self.assertContains(response, '<span class="caregiver-tag tag-pet">Dogs</span>')
        content = response.content.decode()
        self.assertLess(content.index(">Dogs<"), content.index(">Cats<"))

    def test_edit_form_has_cancel_and_no_certifications(self):
        response = self.client.get(
            reverse("edit_caregiver_profile", args=[self.caregiver.pk])
        )
        self.assertContains(response, f'href="{self.url}">Cancel</a>')
        self.assertNotContains(response, "Certifications")

    def test_new_profile_cancel_goes_home(self):
        CaregiverProfile.objects.filter(pk=self.caregiver.pk).delete()
        response = self.client.get(reverse("create_caregiver_profile"))
        self.assertContains(response, f'href="{reverse("home")}">Cancel</a>')
