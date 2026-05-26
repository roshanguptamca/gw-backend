from django.urls import path
from . import views, views_v2

# New V2 API endpoints (recommended)
urlpatterns = [
    # Document management
    path("documents/upload", views_v2.upload_document, name="upload_document_v2"),
    path("documents", views_v2.list_documents, name="list_documents"),
    path("documents/<int:document_id>", views_v2.get_document, name="get_document"),
    path("documents/<int:document_id>/delete", views_v2.delete_document, name="delete_document"),
    # Processing
    path("documents/<int:document_id>/process", views_v2.process_document_endpoint, name="process_document_v2"),
    path("documents/<int:document_id>/status", views_v2.get_processing_status, name="document_status"),
    # Chat
    path("documents/<int:document_id>/chat", views_v2.chat_with_document, name="chat_document"),
    path("documents/<int:document_id>/messages", views_v2.get_chat_messages, name="get_messages"),
    # ====================================================================================
    # OLD API ENDPOINTS (BACKWARD COMPATIBILITY - PRESERVED)
    # ====================================================================================
    path("process/", views.process_document, name="process_document"),
    path("ask/", views.ask, name="ask"),
    path("process-text/", views.process_text, name="process_text"),
    path("ask/remaining/", views.get_remaining_questions, name="get_remaining_questions"),
    path("upload-url/", views.get_upload_url, name="get_upload_url"),
]
