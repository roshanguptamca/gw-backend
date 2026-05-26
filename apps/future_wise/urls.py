from django.urls import path
from .views import ReminderListCreateView, ReminderDetailView, VerifyEmailView

app_name = "future_wise"

urlpatterns = [
    path("reminders/", ReminderListCreateView.as_view(), name="reminder-list-create"),
    path("reminders/<uuid:pk>/", ReminderDetailView.as_view(), name="reminder-detail"),
    path("verify/<str:token>/", VerifyEmailView.as_view(), name="verify-email"),
]
