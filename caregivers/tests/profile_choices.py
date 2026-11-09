"""The services and pet types a caregiver profile needs (both required, as in
the Figma "Update Personal Information (Caregiver)" frame)."""

from caregivers.models import ServiceType
from pets.models import PetType


def required_choices():
    """Form data picking one service and one pet type."""
    service = ServiceType.objects.get_or_create(name="Dog walking")[0]
    dog = PetType.objects.get_or_create(name="Dog")[0]
    return {"selected_services": [service.pk], "supported_pet_types": [dog.pk]}
