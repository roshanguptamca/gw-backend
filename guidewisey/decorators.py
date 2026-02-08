# guidewisey/decorators.py
from functools import wraps
from rest_framework.response import Response
from apps.doc_x.models import Document, UserQuestionLimit

MAX_QUESTIONS_PER_USER = 3  # default

def question_limit(max_questions=MAX_QUESTIONS_PER_USER, use_session=False):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if use_session:
                session_key = request.session.session_key
                if not session_key:
                    request.session.create()
                    session_key = request.session.session_key

                # Create a dummy session-based document
                doc, _ = Document.objects.get_or_create(
                    s3_key=f"SESSION_{session_key}",
                    defaults={"content": "", "summary": ""}
                )

                uq, _ = UserQuestionLimit.objects.get_or_create(
                    user=None,
                    document=doc,
                    session_key=session_key
                )

            else:
                user = request.user
                document_id = request.data.get("document_id")
                if not document_id:
                    return Response({"error": "document_id is required"}, status=400)
                try:
                    doc = Document.objects.get(id=document_id)
                except Document.DoesNotExist:
                    return Response({"error": "Document not found"}, status=404)

                uq, _ = UserQuestionLimit.objects.get_or_create(
                    user=user,
                    document=doc
                )

            if uq.count >= max_questions:
                return Response({"error": "Question limit reached"}, status=403)

            kwargs["document"] = doc
            kwargs["user_question_limit"] = uq
            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator
