from django.shortcuts import render, redirect
from .forms import SignUpForm
from .models import AccountProfile
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required


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
