"""Pet photos show on booking requests for both the owner and the caregiver.

Bug report: a pet's photo was saved, but booking pages still showed only
the pet's first letter.
"""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from .test_bookings import BookingTestData

TEST_MEDIA_ROOT = tempfile.mkdtemp()


def make_photo(name="echo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "orange").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class PetPhotoOnBookingsTests(BookingTestData):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.sitter = get_user_model().objects.create_user(
            "sitter", password="pw-12345!"
        )
        self.caregiver.user = self.sitter
        self.caregiver.save()
        self.pet.photo = make_photo()
        self.pet.save()
        self.booking = self.make_booking()

    def assert_photo_shown(self, response, avatar_class):
        self.assertContains(response, f'src="{self.pet.photo.url}"')
        self.assertContains(
            response, f'class="{avatar_class} theme-{self.pet.theme} has-photo"'
        )

    def test_owner_sees_the_photo_on_my_requests(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assert_photo_shown(response, "booking-avatar")

    def test_owner_sees_the_photo_on_the_request_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.booking.get_absolute_url())
        self.assert_photo_shown(response, "booking-avatar booking-avatar-large")

    def test_caregiver_sees_the_photo_in_the_list_and_panel(self):
        self.client.force_login(self.sitter)
        response = self.client.get(
            reverse("bookings:caregiver_requests"), {"status": "all"}
        )
        self.assert_photo_shown(response, "request-avatar")
        self.assert_photo_shown(response, "request-avatar request-avatar-large")

    def test_caregiver_sees_the_photo_on_the_request_page(self):
        self.client.force_login(self.sitter)
        response = self.client.get(self.booking.get_absolute_url())
        self.assert_photo_shown(response, "booking-avatar booking-avatar-large")

    def test_pets_without_a_photo_keep_their_initial(self):
        self.pet.photo = None
        self.pet.save()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("bookings:booking_list"))
        self.assertNotContains(response, "has-photo")
        self.assertContains(response, ">B</span>")
