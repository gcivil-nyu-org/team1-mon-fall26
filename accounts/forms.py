from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import AccountProfile


class SignUpForm(UserCreationForm):
    error_messages = {
        **UserCreationForm.error_messages,
        "password_mismatch": "Passwords don't match.",
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["placeholder"] = "Your username"
        self.fields["password"].widget.attrs["placeholder"] = "Your password"


class ResetRequestForm(PasswordResetForm):
    """Story #46: ask for a reset link by the email on the account."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["email"]
        field.widget.attrs["placeholder"] = "you@example.com"
        field.error_messages["required"] = "Enter your email."
        field.error_messages["invalid"] = "Enter a valid email address."


class NewPasswordForm(SetPasswordForm):
    """Story #46: choose a new password from the emailed link."""

    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": "Passwords don't match.",
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
