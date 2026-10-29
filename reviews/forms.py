from django import forms

from .models import Review

# Highest first: the stars are laid out right to left so CSS can light up
# every star up to the one picked.
STAR_CHOICES = [(n, f"{n} star{'s' if n != 1 else ''}") for n in range(5, 0, -1)]


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=STAR_CHOICES,
        coerce=int,
        widget=forms.RadioSelect,
        label="Your rating",
        error_messages={"required": "Choose a rating from 1 to 5 stars."},
    )

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 4}),
        }
