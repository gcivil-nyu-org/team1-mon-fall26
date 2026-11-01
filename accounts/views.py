from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .deletion import delete_account
from .forms import DeleteAccountForm, SignUpForm
from .models import AccountProfile


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
            )

            login(request, user)
            return redirect("signup_success")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


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
