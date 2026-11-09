from django import forms


class RestrictForm(forms.Form):
    """#92: why the account is being restricted (optional, admins only)."""

    reason = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "e.g. Reported for harassing messages"}
        ),
    )
