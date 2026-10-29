from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView
from .forms import LoginForm

urlpatterns = [
    path("signup/", views.signup_view, name="signup"),
    path(
        "login/",
        LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=LoginForm,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("signup/success/", views.signup_success_view, name="signup_success"),
]
