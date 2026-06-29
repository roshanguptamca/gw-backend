# apps/doc_x/services/chat_service.py
"""
Chat service - handles chat sessions and messages for documents.
"""
import logging
from typing import List, Optional

from django.contrib.auth import get_user_model

from apps.doc_x.models import ChatMessage, ChatSession, Document, UserQuestionLimit
from services.gemini import GeminiClient

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatService:
    """Service for chat operations on documents."""

    def __init__(self):
        self.ai_client = GeminiClient()

    def get_or_create_session(
        self, document: Document, user: Optional[User] = None, session_key: Optional[str] = None
    ) -> ChatSession:
        """
        Get or create a chat session for a document.

        Args:
            document: Document instance
            user: Optional user
            session_key: Optional session key for anonymous users

        Returns:
            ChatSession instance
        """
        # Try to find existing active session
        query = ChatSession.objects.filter(document=document, is_active=True)

        if user:
            query = query.filter(user=user)
        elif session_key:
            query = query.filter(session_key=session_key)

        session = query.first()

        if not session:
            session = ChatSession.objects.create(
                document=document,
                user=user,
                session_key=session_key,
                title=f"Chat about {document.filename or 'document'}",
            )
            logger.info(f"Created new chat session {session.id} for document {document.id}")

        return session

    def send_message(
        self, session: ChatSession, message: str, user: Optional[User] = None, session_key: Optional[str] = None
    ) -> tuple[ChatMessage, ChatMessage]:
        """
        Send a user message and get AI response.

        Args:
            session: ChatSession instance
            message: User's message
            user: Optional user
            session_key: Optional session key for anonymous users

        Returns:
            Tuple of (user_message, assistant_message)
        """
        # Create user message
        user_msg = ChatMessage.objects.create(session=session, role="user", content=message)

        # Get conversation history
        history = self._get_conversation_history(session)

        # Get document context
        document = session.document
        context = self._build_document_context(document)

        # Generate AI response
        try:
            response = self._generate_response(message, history, context)

            assistant_msg = ChatMessage.objects.create(
                session=session, role="assistant", content=response, model_used="gemini-2.5-flash"
            )

            # Update session timestamp
            session.save()  # Triggers auto_now on updated_at

            logger.info(f"Generated response for session {session.id}")

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            assistant_msg = ChatMessage.objects.create(
                session=session,
                role="assistant",
                content="Sorry, I encountered an error generating a response. Please try again.",
                metadata={"error": str(e)},
            )

        return user_msg, assistant_msg

    def get_messages(self, session: ChatSession, limit: int = 100) -> List[ChatMessage]:
        """
        Get messages for a chat session.

        Args:
            session: ChatSession instance
            limit: Maximum number of messages to return

        Returns:
            List of ChatMessage instances
        """
        return list(session.messages.order_by("created_at")[:limit])

    def check_question_limit(
        self, document: Document, user: Optional[User] = None, session_key: Optional[str] = None, max_questions: int = 3
    ) -> tuple[bool, int]:
        """
        Check if user has reached question limit.

        Args:
            document: Document instance
            user: Optional user
            session_key: Optional session key
            max_questions: Maximum allowed questions

        Returns:
            Tuple of (can_ask, remaining_questions)
        """
        # Get or create question limit tracker
        if user:
            limit_obj, _ = UserQuestionLimit.objects.get_or_create(user=user, document=document, defaults={"count": 0})
        elif session_key:
            limit_obj, _ = UserQuestionLimit.objects.get_or_create(
                user=None, document=document, session_key=session_key, defaults={"count": 0}
            )
        else:
            # No tracking for anonymous without session
            return True, max_questions

        remaining = max_questions - limit_obj.count
        can_ask = remaining > 0

        return can_ask, max(0, remaining)

    def increment_question_count(
        self, document: Document, user: Optional[User] = None, session_key: Optional[str] = None
    ):
        """Increment question count for rate limiting."""
        if user:
            limit_obj, _ = UserQuestionLimit.objects.get_or_create(user=user, document=document, defaults={"count": 0})
        elif session_key:
            limit_obj, _ = UserQuestionLimit.objects.get_or_create(
                user=None, document=document, session_key=session_key, defaults={"count": 0}
            )
        else:
            return

        limit_obj.count += 1
        limit_obj.save()

    def _get_conversation_history(self, session: ChatSession) -> List[dict]:
        """Get conversation history formatted for AI."""
        messages = session.messages.order_by("created_at")
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def _build_document_context(self, document: Document) -> str:
        """Build document context for AI."""
        context_parts = [f"Document: {document.filename or 'Unknown'}"]

        # Add summary if available
        if document.summary:
            context_parts.append(f"\nSummary:\n{document.summary}")

        # Add content or chunks
        if document.content and len(document.content) < 10000:
            context_parts.append(f"\nFull Content:\n{document.content}")
        elif document.chunks.exists():
            # Use first few chunks
            chunks = document.chunks.order_by("chunk_index")[:3]
            context_parts.append("\nContent (excerpt):")
            for chunk in chunks:
                context_parts.append(chunk.content)
        elif document.content:
            # Truncate long content
            context_parts.append(f"\nContent (excerpt):\n{document.content[:5000]}...")

        return "\n".join(context_parts)

    def _generate_response(self, message: str, history: List[dict], context: str) -> str:
        """Generate AI response."""
        system_prompt = (
            "You are a helpful assistant that answers questions about documents. "
            "Use the provided document context to answer the user's question accurately. "
            "If you cannot find the answer in the document, say so clearly."
            f"\n\nDocument Context:\n{context}"
        )

        # Combine message with history
        full_message = message
        if history:
            # Only include recent history to avoid token limits
            recent_history = history[-4:]  # Last 2 exchanges
            history_text = "\n".join([f"{h['role']}: {h['content']}" for h in recent_history])
            full_message = f"Previous conversation:\n{history_text}\n\nCurrent question: {message}"

        response = self.ai_client.explain_text(
            text=full_message, system_prompt=system_prompt, preferred_language="English"
        )

        return response
