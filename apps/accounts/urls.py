from django.urls import path
from .views import (
    LoginView, LogoutView, RegisterView, MeView,
    csrf, session_view, confirm_email_view, ResendConfirmationView,
    ChangePasswordView,
)

urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", MeView.as_view(), name="me"),
    path("csrf/", csrf),
    path("session/", session_view, name="session"),
    path("confirm-email/<str:token>/", confirm_email_view, name="confirm-email"),
    path("resend-confirmation/", ResendConfirmationView.as_view(), name="resend-confirmation"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
