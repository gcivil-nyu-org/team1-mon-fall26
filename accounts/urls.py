from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views
from django.contrib.auth.views import LoginView, LogoutView
from .forms import LoginForm, NewPasswordForm, ResetRequestForm

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
    # Story #48: delete your own account.
    path("delete/", views.delete_account_view, name="delete_account"),
    path("signup/success/", views.signup_success_view, name="signup_success"),
    # Story #46: reset a forgotten password with a link sent by email.
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            form_class=ResetRequestForm,
            email_template_name="accounts/emails/password_reset_email.txt",
            subject_template_name="accounts/emails/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            form_class=NewPasswordForm,
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
