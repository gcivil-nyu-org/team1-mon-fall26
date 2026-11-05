from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .restriction import RESTRICTED_MESSAGE, is_restricted


class RestrictedAccountMiddleware:
    """#92: log a restricted account out on its next request.

    Restricting an account doesn't end sessions that are already open, so
    this does, then shows the reason on the Log in page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and is_restricted(request.user):
            logout(request)
            messages.error(request, RESTRICTED_MESSAGE)
            return redirect("login")
        return self.get_response(request)
