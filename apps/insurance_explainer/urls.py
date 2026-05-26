from django.urls import path
from .views import (
    InsuranceExplainView,
    InsuranceSessionDetailView,
    InsuranceChatView,
    InsuranceMessagesView,
)

urlpatterns = [
    path("sessions/", InsuranceExplainView.as_view(), name="insurance-sessions"),
    path("sessions/<int:pk>/", InsuranceSessionDetailView.as_view(), name="insurance-session-detail"),
    path("sessions/<int:pk>/chat/", InsuranceChatView.as_view(), name="insurance-chat"),
    path("sessions/<int:pk>/messages/", InsuranceMessagesView.as_view(), name="insurance-messages"),
]
