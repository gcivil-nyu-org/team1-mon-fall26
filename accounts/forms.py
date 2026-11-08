from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from caregivers.geocoding import GeocodingUnavailable, geocode

from .models import AccountProfile
from .restriction import RESTRICTED_MESSAGE, is_restricted
from .verification import mark_verified, needs_verification


class SignUpForm(UserCreationForm):
    error_messages = {
        **UserCreationForm.error_messages,
        "password_mismatch": "Passwords don’t match.",
    }

    account_type = forms.ChoiceField(
        choices=[
            (AccountProfile.Role.PET_OWNER, "Pet owner"),
            (AccountProfile.Role.CAREGIVER, "Caregiver"),
        ],
        widget=forms.RadioSelect,
        required=True,
        error_messages={"required": "Choose pet owner or caregiver."},
    )

    email = forms.EmailField(
        required=True,
        error_messages={"required": "Enter your email."},
    )

    first_name = forms.CharField(
        max_length=150,
        required=True,
        error_messages={"required": "Enter your first name."},
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        error_messages={"required": "Enter your last name."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].error_messages["required"] = "Choose a username."
        self.fields["password1"].error_messages["required"] = "Enter a password."
        self.fields["password2"].error_messages["required"] = "Retype your password."

        placeholders = {
            "username": "e.g. samuelee",
            "first_name": "e.g. Sam",
            "last_name": "e.g. Lee",
            "email": "you@example.com",
            "password1": "At least 8 characters",
            "password2": "Type it again",
        }
        for name, placeholder in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = placeholder

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email already has an account.", code="email_taken"
            )
        return email

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]


class DeleteAccountForm(forms.Form):
    """Story #48: confirm account deletion with the current password."""

    password = forms.CharField(
        label="Your password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Your password"}
        ),
        error_messages={"required": "Enter your password to confirm."},
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(
                "That password isn't right.", code="wrong_password"
            )
        return password


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "unverified": "Confirm your email before you log in.",
        "restricted": RESTRICTED_MESSAGE,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unverified_user = None
        self.restricted = False
        self.fields["username"].widget.attrs["placeholder"] = "Your username"
        self.fields["password"].widget.attrs["placeholder"] = "Your password"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        # #92: an admin restricted this account.
        if is_restricted(user):
            self.restricted = True
            raise forms.ValidationError(
                self.error_messages["restricted"], code="restricted"
            )
        # The password was right, but the sign-up email isn't confirmed yet.
        if needs_verification(user):
            self.unverified_user = user
            raise forms.ValidationError(
                self.error_messages["unverified"], code="unverified"
            )


class PersonalInfoForm(forms.Form):
    """#47: a pet owner's name and address, from Kat's "Edit your profile" Figma.

    The email is shown on the page but can't be changed here yet: a new email
    has to be confirmed first, and that step is being added separately.
    The address is looked up with NYC GeoSearch so caregivers can see the
    neighborhood (e.g. "Park Slope, Brooklyn"), never the address itself.
    """

    first_name = forms.CharField(
        max_length=150, error_messages={"required": "Enter your first name."}
    )
    last_name = forms.CharField(
        max_length=150, error_messages={"required": "Enter your last name."}
    )
    address = forms.CharField(
        max_length=255,
        error_messages={"required": "Enter your address."},
        widget=forms.TextInput(attrs={"placeholder": "e.g. 215 6th Ave, Brooklyn"}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        self.profile = user.account_profile
        kwargs.setdefault(
            "initial",
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "address": self.profile.address,
            },
        )
        super().__init__(*args, **kwargs)
        self.location = None
        # Set when GeoSearch can't be reached: the address still saves.
        self.geocoding_unavailable = False

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip()

    def clean_address(self):
        address = self.cleaned_data["address"].strip()
        if address == self.profile.address:
            return address  # Unchanged, so the neighborhood is still right.
        try:
            self.location = geocode(address)
        except GeocodingUnavailable:
            self.geocoding_unavailable = True
            return address
        if self.location is None:
            raise forms.ValidationError(
                "We couldn't find this address in New York City. "
                "Check the house number and street name."
            )
        return address

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.save(update_fields=["first_name", "last_name"])

        self.profile.address = self.cleaned_data["address"]
        if self.location is not None:
            self.profile.neighborhood = ", ".join(
                part
                for part in (self.location.neighborhood, self.location.borough)
                if part
            )
        elif self.geocoding_unavailable:
            # Don't keep showing the old address's neighborhood.
            self.profile.neighborhood = ""
        self.profile.save(update_fields=["address", "neighborhood"])
        return self.profile


class ResendVerificationForm(forms.Form):
    """Ask for a new email verification link."""

    email = forms.EmailField(
        error_messages={
            "required": "Enter your email.",
            "invalid": "Enter a valid email address.",
        },
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com"}),
    )


class ResetRequestForm(PasswordResetForm):
    """Story #46: ask for a reset link by the email on the account."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["email"]
        field.widget.attrs["placeholder"] = "you@example.com"
        field.error_messages["required"] = "Enter your email."
        field.error_messages["invalid"] = "Enter a valid email."


class NewPasswordForm(SetPasswordForm):
    """Story #46: choose a new password from the emailed link."""

    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": "Passwords don’t match.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs[
            "placeholder"
        ] = "At least 8 characters"
        self.fields["new_password2"].widget.attrs["placeholder"] = "Type it again"
        self.fields["new_password1"].error_messages[
            "required"
        ] = "Enter a new password."
        self.fields["new_password2"].error_messages[
            "required"
        ] = "Retype your new password."

    def save(self, commit=True):
        user = super().save(commit)
        # The reset link came to their inbox, so the email is theirs.
        mark_verified(user)
        return user
