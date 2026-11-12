from django import forms

from .models import BODY_LENGTH, TITLE_LENGTH, Post


class PostForm(forms.ModelForm):
    """#67 Create Forum Post: a title and the post itself, both required."""

    class Meta:
        model = Post
        fields = ["title", "body"]
        labels = {"title": "Title", "body": "Post"}
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "e.g. Best cafes that welcome dogs"}
            ),
            "body": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": "Share a tip, a question or a pet-friendly find.",
                }
            ),
        }
        error_messages = {
            "title": {
                "required": "Enter a title.",
                "max_length": f"Keep the title under {TITLE_LENGTH} characters.",
            },
            "body": {
                "required": "Write your post.",
                "max_length": f"Keep your post under {BODY_LENGTH} characters.",
            },
        }

    def clean_title(self):
        return self.cleaned_data["title"].strip()

    def clean_body(self):
        return self.cleaned_data["body"].strip()
