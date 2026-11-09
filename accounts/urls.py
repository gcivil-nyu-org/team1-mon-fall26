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
    # #47: a pet owner's profile and personal info.
    path("profile/", views.my_profile_view, name="my_profile"),
    path("profile/edit/", views.edit_profile_view, name="edit_profile"),
    path(
        "profile/email/<str:token>/",
        views.confirm_email_change_view,
        name="confirm_email_change",
    ),
    # Story #48: delete your own account.
    path("delete/", views.delete_account_view, name="delete_account"),
    path("signup/success/", views.signup_success_view, name="signup_success"),
    # Sign-up email verification.
    path("verify-email/sent/", views.verify_email_sent_view, name="verify_email_sent"),
    path(
        "verify-email/resend/",
        views.resend_verification_view,
        name="resend_verification",
    ),
    path("verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    # Story #46: reset a forgotten password with a link sent by email.
    path(
        "password-reset/",
        views.ResetRequestView.as_view(
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
        views.ResetSentView.as_view(template_name="accounts/password_reset_done.html"),
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
