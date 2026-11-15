from django import forms

from .models import MAX_MESSAGE_LENGTH, MAX_TITLE_LENGTH, Announcement

# The Figma's error wording, under each field.
REQUIRED = {
    "title": "Add a title.",
    "kind": "Pick a type.",
    "audience": "Pick who sees it.",
    "message": "Add a message.",
}


class AnnouncementForm(forms.ModelForm):
    """Publishing needs every field. A draft only needs a title, so an admin
    can save one half-written."""

    class Meta:
        model = Announcement
        fields = ["title", "kind", "audience", "message"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "maxlength": MAX_TITLE_LENGTH,
                    "placeholder": "e.g. Scheduled maintenance Sunday",
                }
            ),
            "kind": forms.RadioSelect,
            "audience": forms.RadioSelect,
            "message": forms.Textarea(
                attrs={
                    "rows": 4,
                    "maxlength": MAX_MESSAGE_LENGTH,
                    "placeholder": "What do users need to know?",
                }
            ),
        }

    def __init__(self, *args, publishing=True, **kwargs):
        super().__init__(*args, **kwargs)
        # No empty "---------" choice for the chips.
        self.fields["kind"].choices = Announcement.Kind.choices
        self.fields["audience"].choices = Announcement.Audience.choices
        for name, field in self.fields.items():
            field.required = publishing or name == "title"
            field.error_messages["required"] = REQUIRED[name]

    def clean_title(self):
        return self.cleaned_data["title"].strip()

    def clean_message(self):
        return self.cleaned_data["message"].strip()
