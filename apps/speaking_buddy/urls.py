from django.urls import path

from .views import (
    buddy_avatar_view,
    buddy_history_view,
    buddy_memory_detail_view,
    buddy_memory_view,
    buddy_profile_view,
    buddy_realtime_token_view,
    buddy_session_end_view,
    buddy_session_message_view,
    buddy_session_start_view,
    buddy_session_view,
    buddy_settings_view,
)

urlpatterns = [
    path("profile/", buddy_profile_view),
    path("settings/", buddy_settings_view),
    path("avatar/", buddy_avatar_view),
    path("memory/", buddy_memory_view),
    path("memory/<int:pk>/", buddy_memory_detail_view),
    path("history/", buddy_history_view),
    path("session/", buddy_session_view),
    path("session/start/", buddy_session_start_view),
    path("session/end/", buddy_session_end_view),
    path("session/message/", buddy_session_message_view),
    path("realtime-token/", buddy_realtime_token_view),
]

