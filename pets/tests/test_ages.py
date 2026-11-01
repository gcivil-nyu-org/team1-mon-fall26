"""Pet ages: stored as a birth date, shown as "2 years", "2 yrs" or "5 months"."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from ..forms import PetForm, subtract_months
from ..models import Pet, PetType


def pet_aged(months):
    return Pet(name="Milo", date_of_birth=subtract_months(date.today(), months))


class SubtractMonthsTests(SimpleTestCase):
    def test_same_day_in_an_earlier_month(self):
        self.assertEqual(subtract_months(date(2026, 10, 15), 2), date(2026, 8, 15))

    def test_crosses_the_year(self):
        self.assertEqual(subtract_months(date(2026, 1, 10), 3), date(2025, 10, 10))

    def test_clamps_to_the_end_of_a_shorter_month(self):
        self.assertEqual(subtract_months(date(2026, 3, 31), 1), date(2026, 2, 28))
        self.assertEqual(subtract_months(date(2024, 3, 31), 1), date(2024, 2, 29))


class AgeDisplayTests(SimpleTestCase):
    def test_no_birth_date(self):
        pet = Pet(name="Milo")
        self.assertIsNone(pet.age_years)
        self.assertEqual(pet.age_display, "")
        self.assertEqual(pet.age_short, "")

    def test_short_age_for_cards(self):
        self.assertEqual(pet_aged(0).age_short, "Under 1 mo")
        self.assertEqual(pet_aged(1).age_short, "1 mo")
        self.assertEqual(pet_aged(5).age_short, "5 mos")
        self.assertEqual(pet_aged(12).age_short, "1 yr")
        self.assertEqual(pet_aged(30).age_short, "2 yrs")

    def test_full_age(self):
        self.assertEqual(pet_aged(0).age_display, "Under 1 month")
        self.assertEqual(pet_aged(1).age_display, "1 month")
        self.assertEqual(pet_aged(13).age_display, "1 year")


class EditFormAgeTests(TestCase):
    def test_young_pet_is_shown_in_months_when_editing(self):
        owner = get_user_model().objects.create_user("alex", password="pass12345")
        pet = Pet.objects.create(
            owner=owner,
            name="Pip",
            pet_type=PetType.objects.get(name="Rabbit"),
            date_of_birth=subtract_months(date.today(), 5),
        )
        form = PetForm(instance=pet)
        self.assertEqual(form.initial["age"], 5)
        self.assertEqual(form.initial["age_unit"], "months")
