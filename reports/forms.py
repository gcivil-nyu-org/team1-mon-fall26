from django import forms

from .models import MAX_DETAILS_LENGTH, Report


class ReportForm(forms.ModelForm):
    reason = forms.ChoiceField(
        choices=Report.Reason.choices,
        widget=forms.RadioSelect,
        label="Why are you reporting this?",
        error_messages={"required": "Choose a reason."},
    )
    details = forms.CharField(
        label="Anything else we should know?",
        required=False,
        max_length=MAX_DETAILS_LENGTH,
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": MAX_DETAILS_LENGTH}),
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
