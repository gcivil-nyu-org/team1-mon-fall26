from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .deletion import delete_account
from .forms import (
    DeleteAccountForm,
    NeighborhoodForm,
    ResendVerificationForm,
    SignUpForm,
)
from .models import AccountProfile
from .verification import (
    mark_verified,
    needs_verification,
    send_verification_email,
    user_from_token,
)

SENT_TO = "verify_email_sent_to"
RESET_SENT_TO = "password_reset_sent_to"


def home_view(request):
    """Send people to their own start page: log in, My pets, or caregiver requests."""
    user = request.user
    if not user.is_authenticated:
        return redirect("login")
    profile = getattr(user, "account_profile", None)
    if hasattr(user, "caregiver_profile") or (profile and profile.role == "caregiver"):
        return redirect("bookings:caregiver_requests")
    return redirect("pets:list")


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()

            AccountProfile.objects.create(
                user=user,
                role=form.cleaned_data["account_type"],
                email_verified=False,
            )

            # The account works once they click the link we email them.
            send_verification_email(request, user)
            request.session[SENT_TO] = user.email
            return redirect("verify_email_sent")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


def verify_email_sent_view(request):
    """'Check your email' after signing up, with a way to get a new link."""
    return render(
        request,
        "accounts/verify_email_sent.html",
        {
            "email": request.session.get(SENT_TO, ""),
            "form": ResendVerificationForm(),
        },
    )


@require_POST
def resend_verification_view(request):
    form = ResendVerificationForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "accounts/verify_email_sent.html",
            {"email": request.session.get(SENT_TO, ""), "form": form},
        )
    email = form.cleaned_data["email"]
    user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if user is not None and needs_verification(user):
        send_verification_email(request, user)
    # Same answer whether or not the email has an account waiting.
    request.session[SENT_TO] = email
    messages.success(request, "We sent you a new link.")
    return redirect("verify_email_sent")


def verify_email_view(request, token):
    user = user_from_token(token)
    if user is None:
        return render(
            request,
            "accounts/verify_email_invalid.html",
            {"form": ResendVerificationForm()},
        )
    if not needs_verification(user):
        messages.success(request, "Your email is already confirmed. Log in below.")
        return redirect("login")
    mark_verified(user)
    request.session.pop(SENT_TO, None)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("signup_success")


@login_required
def signup_success_view(request):
    profile = request.user.account_profile

    return render(
        request,
        "accounts/signup_success.html",
        {
            "first_name": request.user.first_name or request.user.username,
            "is_caregiver": profile.role == "caregiver",
        },
    )


class ResetRequestView(auth_views.PasswordResetView):
    """Story #46: remember the typed email for the 'Check your email' page."""

    def form_valid(self, form):
        # Same answer whether or not the email has an account.
        self.request.session[RESET_SENT_TO] = form.cleaned_data["email"]
        return super().form_valid(form)


class ResetSentView(auth_views.PasswordResetDoneView):
    """'Check your email' after asking for a reset link."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["email"] = self.request.session.get(RESET_SENT_TO, "")
        return context


@login_required
def neighborhood_view(request):
    """A pet owner sets the neighborhood caregivers see in Messages."""
    profile, _ = AccountProfile.objects.get_or_create(user=request.user)
    if (
        hasattr(request.user, "caregiver_profile")
        or profile.role == AccountProfile.Role.CAREGIVER
    ):
        return redirect("home")
    form = NeighborhoodForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your neighborhood is saved.")
        return redirect("neighborhood")
    return render(request, "accounts/neighborhood.html", {"form": form})


@login_required
def delete_account_view(request):
    """Story #48: confirm with the password, then the account is deleted."""
    if request.method == "POST":
        form = DeleteAccountForm(request.POST, user=request.user)
        if form.is_valid():
            delete_account(request.user)
            logout(request)
            messages.success(request, "Your PawPal account has been deleted.")
            return redirect("login")
    else:
        form = DeleteAccountForm(user=request.user)
    return render(request, "accounts/delete_account.html", {"form": form})
