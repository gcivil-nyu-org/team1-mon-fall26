"""Template helpers for account pages."""

from django import template

from ..forms import DeleteAccountForm

register = template.Library()


@register.simple_tag(takes_context=True)
def delete_account_form(context):
    """An empty Delete account form for the pop-up on the profile pages."""
    return DeleteAccountForm(user=context["request"].user)
