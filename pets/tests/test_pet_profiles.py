import io
import shutil
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from ..forms import subtract_months
from ..models import PET_THEMES, Pet, PetType

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp()


def make_photo(name="pepper.png", size=(20, 20)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "pink").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class PetTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.owner = User.objects.create_user(username="alex", password="pass12345")
        self.other_owner = User.objects.create_user(
            username="sam", password="pass12345"
        )
        self.dog = PetType.objects.get(name="Dog")
        self.rabbit = PetType.objects.get(name="Rabbit")
        self.client.login(username="alex", password="pass12345")

    def make_pet(
        self, owner=None, name="Milo", pet_type=None, months_old=None, **extra
    ):
        born = None
        if months_old is not None:
            born = subtract_months(date.today(), months_old)
        return Pet.objects.create(
            owner=owner or self.owner,
            name=name,
            pet_type=pet_type or self.dog,
            date_of_birth=born,
            **extra,
        )


class PetTypeTests(TestCase):
    def test_design_pet_types_are_created_by_migration(self):
        names = set(PetType.objects.values_list("name", flat=True))
        self.assertTrue({"Dog", "Cat", "Bird", "Rabbit", "Fish", "Other"} <= names)


class PetModelTests(PetTestBase):
    def test_str_shows_name_and_type(self):
        self.assertEqual(str(self.make_pet()), "Milo (Dog)")

    def test_age_display_in_years(self):
        self.assertEqual(self.make_pet(months_old=24).age_display, "2 years")
        self.assertEqual(self.make_pet(months_old=12).age_display, "1 year")

    def test_age_display_in_months(self):
        self.assertEqual(self.make_pet(months_old=5).age_display, "5 months")
        self.assertEqual(self.make_pet(months_old=0).age_display, "Under 1 month")

    def test_age_display_empty_without_date_of_birth(self):
        self.assertEqual(self.make_pet().age_display, "")

    def test_each_pet_keeps_one_color_and_neighbors_differ(self):
        first, second = self.make_pet(), self.make_pet()
        self.assertIn(first.theme, PET_THEMES)
        self.assertEqual(first.theme, Pet.objects.get(pk=first.pk).theme)
        self.assertNotEqual(first.theme, second.theme)

    def test_subtract_months_handles_short_months(self):
        self.assertEqual(subtract_months(date(2026, 3, 31), 1), date(2026, 2, 28))
        self.assertEqual(subtract_months(date(2026, 1, 15), 13), date(2024, 12, 15))


class PetCreateViewTests(PetTestBase):
    url = reverse("pets:create")

    def valid_data(self, **overrides):
        data = {
            "name": "Pepper",
            "pet_type": self.rabbit.pk,
            "age": 2,
            "age_unit": "years",
            "special_care_instructions": "Hay twice a day",
        }
        data.update(overrides)
        return data

    def test_form_page_shows_pet_type_chips_in_design_order(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        choices = response.context["form"].fields["pet_type"].choices
        labels = [label for _, label in choices]
        self.assertEqual(labels[:5], ["Dog", "Cat", "Bird", "Rabbit", "Fish"])
        self.assertEqual(labels[-1], "Other")

    def test_valid_form_creates_pet_for_logged_in_owner(self):
        response = self.client.post(self.url, self.valid_data())

        pet = Pet.objects.get(name="Pepper")
        self.assertEqual(pet.owner, self.owner)
        self.assertEqual(pet.pet_type, self.rabbit)
        self.assertEqual(pet.age_display, "2 years")
        self.assertEqual(pet.special_care_instructions, "Hay twice a day")
        self.assertRedirects(response, f"{reverse('pets:list')}?new={pet.pk}")

    def test_age_in_months(self):
        self.client.post(self.url, self.valid_data(age=5, age_unit="months"))
        self.assertEqual(Pet.objects.get(name="Pepper").age_display, "5 months")

    def test_care_needs_is_optional(self):
        self.client.post(self.url, self.valid_data(special_care_instructions=""))
        self.assertTrue(Pet.objects.filter(name="Pepper").exists())

    def test_missing_required_fields_show_design_error_messages(self):
        response = self.client.post(self.url, {"age_unit": "years"})
        self.assertEqual(Pet.objects.count(), 0)
        self.assertContains(response, "Almost there.")
        self.assertContains(response, "Enter your pet&#x27;s name.")
        self.assertContains(response, "Choose or enter a pet type.")
        self.assertContains(response, "Enter your pet&#x27;s age as a number.")

    def test_negative_or_huge_age_is_rejected(self):
        self.client.post(self.url, self.valid_data(age=-1))
        self.client.post(self.url, self.valid_data(age=99))
        self.assertEqual(Pet.objects.count(), 0)


class PetPhotoTests(PetTestBase):
    url = reverse("pets:create")

    def data(self, **extra):
        base = {
            "name": "Pepper",
            "pet_type": self.rabbit.pk,
            "age": 2,
            "age_unit": "years",
        }
        base.update(extra)
        return base

    def test_photo_is_optional(self):
        self.client.post(self.url, self.data())
        self.assertFalse(Pet.objects.get(name="Pepper").photo)

    def test_photo_upload_is_saved_and_shown(self):
        self.client.post(self.url, self.data(photo=make_photo()))
        pet = Pet.objects.get(name="Pepper")
        self.assertTrue(pet.photo.name.startswith("pets/photos/"))

        for page in (reverse("pets:list"), pet.get_absolute_url()):
            self.assertContains(self.client.get(page), pet.photo.url)

    def test_non_image_file_is_rejected(self):
        fake = SimpleUploadedFile(
            "notes.txt", b"not an image", content_type="text/plain"
        )
        response = self.client.post(self.url, self.data(photo=fake))
        self.assertFalse(Pet.objects.exists())
        self.assertIn("photo", response.context["form"].errors)

    def test_photo_over_size_limit_is_rejected(self):
        # With a 0 MB limit, any real file counts as too big.
        with patch("pets.forms.MAX_PHOTO_MB", 0):
            response = self.client.post(self.url, self.data(photo=make_photo()))
        self.assertFalse(Pet.objects.exists())
        self.assertIn("smaller than", response.context["form"].errors["photo"][0])

    def test_edit_can_remove_photo(self):
        self.client.post(self.url, self.data(photo=make_photo()))
        pet = Pet.objects.get(name="Pepper")
        self.client.post(
            reverse("pets:edit", args=[pet.pk]), self.data(remove_photo="on")
        )
        pet.refresh_from_db()
        self.assertFalse(pet.photo)

    def test_edit_without_new_photo_keeps_existing_photo(self):
        self.client.post(self.url, self.data(photo=make_photo()))
        pet = Pet.objects.get(name="Pepper")
        self.client.post(reverse("pets:edit", args=[pet.pk]), self.data(age=3))
        pet.refresh_from_db()
        self.assertTrue(pet.photo)


class PetListViewTests(PetTestBase):
    url = reverse("pets:list")

    def test_shows_only_the_owners_pets(self):
        self.make_pet(name="Milo")
        self.make_pet(owner=self.other_owner, name="Shadow")

        response = self.client.get(self.url)
        self.assertContains(response, "Milo")
        self.assertNotContains(response, "Shadow")

    def test_newest_pet_first_with_new_badge_and_message(self):
        self.make_pet(name="Biscuit")
        response = self.client.post(
            reverse("pets:create"),
            {
                "name": "Pepper",
                "pet_type": self.rabbit.pk,
                "age": 2,
                "age_unit": "years",
            },
            follow=True,
        )
        pets = list(response.context["pets"])
        self.assertEqual(pets[0].name, "Pepper")
        self.assertContains(response, "New!")
        self.assertContains(response, "Pepper&#x27;s profile was created.")

    def test_empty_state_when_owner_has_no_pets(self):
        response = self.client.get(self.url)
        self.assertContains(response, "No pets yet")


class PetDetailViewTests(PetTestBase):
    def test_owner_can_view_their_pet(self):
        pet = self.make_pet(
            name="Pepper",
            pet_type=self.rabbit,
            months_old=24,
            special_care_instructions="Hay twice a day",
        )
        response = self.client.get(pet.get_absolute_url())
        self.assertContains(response, "Pepper")
        self.assertContains(response, "Rabbit · 2 years old")
        self.assertContains(response, "Hay twice a day")

    def test_cannot_view_another_owners_pet(self):
        pet = self.make_pet(owner=self.other_owner, name="Shadow")
        response = self.client.get(pet.get_absolute_url())
        self.assertEqual(response.status_code, 404)


class PetUpdateViewTests(PetTestBase):
    def test_edit_form_shows_current_age(self):
        pet = self.make_pet(months_old=24)
        response = self.client.get(reverse("pets:edit", args=[pet.pk]))
        form = response.context["form"]
        self.assertEqual(form.initial["age"], 2)
        self.assertEqual(form.initial["age_unit"], "years")

    def test_owner_can_update_their_pet(self):
        pet = self.make_pet(name="Milo", months_old=24)
        response = self.client.post(
            reverse("pets:edit", args=[pet.pk]),
            {
                "name": "Milo",
                "pet_type": self.dog.pk,
                "age": 3,
                "age_unit": "years",
                "special_care_instructions": "Now on a diet",
            },
        )
        pet.refresh_from_db()
        self.assertRedirects(response, pet.get_absolute_url())
        self.assertEqual(pet.age_display, "3 years")
        self.assertEqual(pet.special_care_instructions, "Now on a diet")

    def test_cannot_edit_another_owners_pet(self):
        pet = self.make_pet(owner=self.other_owner, name="Shadow")
        response = self.client.get(reverse("pets:edit", args=[pet.pk]))
        self.assertEqual(response.status_code, 404)


class PetLoginRequiredTests(TestCase):
    def test_logged_out_users_are_redirected_to_login(self):
        for name in ("pets:list", "pets:create"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)
