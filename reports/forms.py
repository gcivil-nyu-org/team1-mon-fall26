from django import forms

from .models import MAX_DETAILS_LENGTH, Report


class ReportForm(forms.ModelForm):
    reason = forms.ChoiceField(
        choices=Report.Reason.choices,
        widget=forms.RadioSelect,
        label="Reason",
        error_messages={"required": "Choose a reason."},
    )
    details = forms.CharField(
        label="More details",
        required=False,
        max_length=MAX_DETAILS_LENGTH,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "maxlength": MAX_DETAILS_LENGTH,
                "placeholder": "Anything else we should know?",
            }
        ),
        error_messages={
            "max_length": f"Keep it under {MAX_DETAILS_LENGTH} characters.",
        },
    )

    class Meta:
        model = Report
        fields = ["reason", "details"]

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("reason") == Report.Reason.OTHER
            and not cleaned.get("details", "").strip()
        ):
            self.add_error("details", "Tell us a little about what's wrong.")
        return cleaned
