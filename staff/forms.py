from django import forms


class RestrictForm(forms.Form):
    """#92: why the account is being restricted. Required, as in the Figma;
    only admins see it."""

    reason = forms.CharField(
        max_length=300,
        error_messages={"required": "Add a reason for restricting the account."},
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "e.g. Sent rude messages to a pet owner."}
        ),
    )
