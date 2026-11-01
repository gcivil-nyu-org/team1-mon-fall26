from django import forms

from .models import Review

MAX_REVIEW_LENGTH = 500

# Highest first: the paws are laid out right to left so CSS can light up
# every paw up to the one picked.
RATING_CHOICES = [(n, f"{n} out of 5") for n in range(5, 0, -1)]


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=RATING_CHOICES,
        coerce=int,
        widget=forms.RadioSelect,
        label="Rating",
        error_messages={"required": "Choose a rating from 1 to 5."},
    )
    comment = forms.CharField(
        label="Review",
        required=False,
        max_length=MAX_REVIEW_LENGTH,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": MAX_REVIEW_LENGTH}),
        error_messages={
            "max_length": f"Keep your review under {MAX_REVIEW_LENGTH} characters."
        },
    )

    class Meta:
        model = Review
        fields = ["rating", "comment"]
