"""Stories #22 (add temperament information) and #87 (view pet temperament)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from caregivers.models import CaregiverProfile, ServiceType

from ..models import Pet, PetType

User = get_user_model()


class OwnerTemperamentTests(TestCase):
    """#22: the owner describes the pet's temperament."""

    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        self.client.login(username="alex", password="pass12345")
        self.dog = PetType.objects.get(name="Dog")

    def form_data(self, **overrides):
        data = {"name": "Milo", "pet_type": self.dog.pk, "age": 3, "age_unit": "years"}
        data.update(overrides)
        return data

    def test_form_has_a_temperament_section(self):
        response = self.client.get(reverse("pets:create"))
        self.assertContains(response, "Temperament")
        self.assertContains(response, 'value="good_with_kids"')
        self.assertContains(response, "Behavior notes &amp; preferences")

    def test_traits_and_notes_are_saved_to_the_pet(self):
        self.client.post(
            reverse("pets:create"),
            self.form_data(
                temperament_traits=["friendly", "shy"],
                behavior_notes="Loves belly rubs",
            ),
        )
        pet = Pet.objects.get(name="Milo")
        self.assertEqual(sorted(pet.temperament_traits), ["friendly", "shy"])
        self.assertEqual(pet.behavior_notes, "Loves belly rubs")
        self.assertEqual(pet.temperament_labels, ["Friendly", "Shy with strangers"])

    def test_temperament_is_optional(self):
        response = self.client.post(reverse("pets:create"), self.form_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Pet.objects.get(name="Milo").temperament_traits, [])

    def test_unknown_trait_is_rejected(self):
        response = self.client.post(
            reverse("pets:create"), self.form_data(temperament_traits=["grumpy"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pet.objects.exists())

    def test_owner_can_update_it_later(self):
        pet = Pet.objects.create(
            owner=self.owner,
            name="Milo",
            pet_type=self.dog,
            temperament_traits=["anxious"],
            behavior_notes="Hides under the bed",
        )
        edit = reverse("pets:edit", args=[pet.pk])
        response = self.client.get(edit)
        self.assertContains(
            response, 'value="anxious" id="id_temperament_traits_7" checked'
        )
        self.assertContains(response, "Hides under the bed")

        self.client.post(
            edit,
            self.form_data(
                temperament_traits=["calm"], behavior_notes="Much calmer now"
            ),
        )
        pet.refresh_from_db()
        self.assertEqual(pet.temperament_traits, ["calm"])
        self.assertEqual(pet.behavior_notes, "Much calmer now")

    def test_owner_page_shows_temperament(self):
        pet = Pet.objects.create(
            owner=self.owner,
            name="Milo",
            pet_type=self.dog,
            temperament_traits=["good_with_kids"],
            behavior_notes="Pulls toward squirrels",
        )
        response = self.client.get(pet.get_absolute_url())
        self.assertContains(response, "Good with kids")
        self.assertContains(response, "Pulls toward squirrels")

    def test_owner_page_says_when_nothing_added(self):
        pet = Pet.objects.create(owner=self.owner, name="Milo", pet_type=self.dog)
        self.assertContains(
            self.client.get(pet.get_absolute_url()), "No temperament details yet."
        )


class CaregiverTemperamentTests(TestCase):
    """#87: the caregiver sees the right pet's temperament."""

    def setUp(self):
        self.owner = User.objects.create_user("alex", password="pass12345")
        carer = User.objects.create_user("chloe", password="pass12345")
        self.caregiver = CaregiverProfile.objects.create(
            user=carer, name="Chloe Shih", service_area="Brooklyn"
        )
        dog = PetType.objects.get(name="Dog")
        self.milo = Pet.objects.create(
            owner=self.owner,
            name="Milo",
            pet_type=dog,
            temperament_traits=["reactive"],
            behavior_notes="Keep him away from other dogs",
        )
        self.rex = Pet.objects.create(
            owner=self.owner,
            name="Rex",
            pet_type=dog,
            temperament_traits=["cuddly"],
            behavior_notes="Will sit on your lap",
        )
        self.client.login(username="chloe", password="pass12345")

    def book(self, pet, status):
        start = timezone.now() + timedelta(days=1)
        return Booking.objects.create(
            owner=self.owner,
            pet=pet,
            caregiver=self.caregiver,
            service_type=ServiceType.objects.get(name="Dog walking"),
            start_time=start,
            end_time=start + timedelta(hours=1),
            status=status,
        )

    def test_pet_profile_shows_the_pets_temperament(self):
        self.book(self.milo, Booking.Status.ACCEPTED)
        response = self.client.get(reverse("pets:care_view", args=[self.milo.pk]))
        self.assertContains(response, "Reactive to other animals")
        self.assertContains(response, "Keep him away from other dogs")
        self.assertNotContains(response, "Will sit on your lap")

    def test_request_panel_shows_temperament(self):
        self.book(self.milo, Booking.Status.PENDING)
        response = self.client.get(reverse("bookings:caregiver_requests"))
        self.assertContains(response, "Reactive to other animals.")
        self.assertContains(response, "Keep him away from other dogs")
