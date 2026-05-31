from django.urls import path
from .views import (
    NotificationPreferencesView,
    ReminderDeliveryStatusView,
    ReminderDetailView,
    ReminderListCreateView,
    ReminderTestSendView,
    TelegramWebhookView,
    VerifyEmailView,
)

app_name = "future_wise"

urlpatterns = [
    # Core reminder CRUD
    path("reminders/", ReminderListCreateView.as_view(), name="reminder-list-create"),
    path("reminders/<uuid:pk>/", ReminderDetailView.as_view(), name="reminder-detail"),

    # Multi-channel extras
    path("reminders/<uuid:pk>/test/", ReminderTestSendView.as_view(), name="reminder-test-send"),
    path("reminders/<uuid:pk>/delivery-status/", ReminderDeliveryStatusView.as_view(), name="reminder-delivery-status"),

    # Email verification
    path("verify/<str:token>/", VerifyEmailView.as_view(), name="verify-email"),

    # User notification preferences
    path("notification-preferences/", NotificationPreferencesView.as_view(), name="notification-preferences"),

    # Telegram Bot webhook
    path("telegram/webhook/", TelegramWebhookView.as_view(), name="telegram-webhook"),
]
