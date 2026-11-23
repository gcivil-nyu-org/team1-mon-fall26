"""Fixes for pet profile issues other teams found at the testing party:
deleting a pet with a care post (#322), the form banner (#302) and an age in
months coming back as years (#308)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from caregivers.models import ServiceType
from opportunities.models import CareOpportunity

from ..forms import PetForm
from ..models import Pet, PetType

User = get_user_model()


class PetFixData(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.client.force_login(self.owner)
        self.dog = PetType.objects.get(name="Dog")
        self.pet = Pet.objects.create(
            owner=self.owner, name="TempPet", pet_type=self.dog
        )


class DeleteWithCarePostTests(PetFixData):
    def post_care(self, starts_in, status="open"):
        start = timezone.now() + starts_in
        return CareOpportunity.objects.create(
            owner=self.owner,
            pet=self.pet,
            service_type=ServiceType.objects.get(name="Dog walking"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            location="Park Slope",
            status=status,
        )

    def delete(self):
        return self.client.post(reverse("pets:delete", args=[self.pet.pk]), follow=True)

    def test_open_care_post_blocks_the_delete(self):
        self.post_care(timedelta(days=2))
        response = self.delete()
        self.assertContains(response, "has an open care post")
        self.assertIsNone(Pet.objects.get(pk=self.pet.pk).deleted_at)

    def test_closed_or_past_care_post_hides_the_pet(self):
        self.post_care(timedelta(days=2), status="closed")
        self.post_care(-timedelta(days=2))
        response = self.delete()
        self.assertContains(response, "profile was deleted")
        self.assertIsNotNone(Pet.objects.get(pk=self.pet.pk).deleted_at)


class BannerTests(PetFixData):
    def test_invalid_values_are_not_called_blank(self):
        response = self.client.post(
            reverse("pets:create"),
            {
                "name": "Milo",
                "pet_type": self.dog.pk,
                "age": "999",
                "age_unit": "years",
                "vet_phone": "call me maybe",
            },
        )
        self.assertContains(response, "Check the highlighted fields.")
        self.assertNotContains(response, "be left blank")

    def test_blank_required_field(self):
        response = self.client.post(reverse("pets:create"), {"age_unit": "years"})
        self.assertContains(response, "be left blank")


class AgeRoundTripTests(PetFixData):
    def form_for(self, months):
        today = timezone.localdate()
        year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
        self.pet.date_of_birth = today.replace(year=year, month=month + 1, day=1)
        return PetForm(instance=self.pet)

    def test_months_stay_months(self):
        form = self.form_for(18)
        self.assertEqual(
            (form.initial["age"], form.initial["age_unit"]), (18, "months")
        )

    def test_whole_years_and_older_pets_show_years(self):
        form = self.form_for(12)
        self.assertEqual((form.initial["age"], form.initial["age_unit"]), (1, "years"))
        form = self.form_for(30)
        self.assertEqual((form.initial["age"], form.initial["age_unit"]), (2, "years"))

    def test_young_pets_show_months(self):
        form = self.form_for(5)
        self.assertEqual((form.initial["age"], form.initial["age_unit"]), (5, "months"))
