from django.urls import path
from .views import LoginView, LogoutView, RegisterView ,MeView, csrf, session_view
urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", MeView.as_view(), name="me"),
    path("csrf/", csrf),
path("session/", session_view, name="session"),
]
