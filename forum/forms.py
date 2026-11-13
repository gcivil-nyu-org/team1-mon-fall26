from django import forms

from .models import BODY_LENGTH, COMMENT_LENGTH, TITLE_LENGTH, Comment, Post


class PostForm(forms.ModelForm):
    """#67 Create Forum Post, as in the Figma "New post" popup: a title, a
    topic and the details, all required."""

    topic = forms.ChoiceField(
        label="Topic",
        choices=Post.Topic.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Pick a topic.", "invalid_choice": "Pick a topic."},
    )

    class Meta:
        model = Post
        fields = ["title", "topic", "body"]
        labels = {"title": "Title", "body": "Details"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "What\u2019s it about?"}),
            "body": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Share a spot, a tip, or ask a question",
                }
            ),
        }
        error_messages = {
            "title": {
                "required": "Add a title.",
                "max_length": f"Keep the title under {TITLE_LENGTH} characters.",
            },
            "body": {
                "required": "Add some details.",
                "max_length": f"Keep it under {BODY_LENGTH} characters.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No topic is picked until the person picks one (the model's default
        # is only for posts written before topics existed).
        self.initial.pop("topic", None)

    def clean_title(self):
        return self.cleaned_data["title"].strip()

    def clean_body(self):
        return self.cleaned_data["body"].strip()


class CommentForm(forms.ModelForm):
    """#69 Comment on Forum Posts."""

    class Meta:
        model = Comment
        fields = ["body"]
        labels = {"body": "Add a comment"}
        widgets = {
            "body": forms.TextInput(
                attrs={"placeholder": "Add a comment…", "autocomplete": "off"}
            )
        }
        error_messages = {
            "body": {
                "required": "Write a comment first.",
                "max_length": f"Keep your comment under {COMMENT_LENGTH} characters.",
            }
        }

    def clean_body(self):
        return self.cleaned_data["body"].strip()
