import os
import logging
from typing import List, Optional
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AIClient:
    """
    Lightweight LLM client for explaining documents and answering questions.
    Pure service: no Django, no DB, no S3 dependency.
    """

    DEFAULT_SYSTEM_PROMPT = (
        "You explain government, school, and official documents "
        "in very simple, clear language."
    )

    def __init__(self):
        """
        Initialize OpenAI client at runtime.
        This MUST NOT fail during Django startup or migrations.
        """
        self.api_key = os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            logger.warning(
                "OPENAI_API_KEY not set. AIClient will be disabled until provided."
            )
            self.client = None
            return

        try:
            self.client = OpenAI(api_key=self.api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as exc:
            logger.error(f"Failed to initialize OpenAI client: {exc}")
            self.client = None
            raise

    def explain_text(
        self,
        text: str,
        conversation: Optional[List[dict]] = None,
        system_prompt: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
    ) -> str:
        """
        Explain or answer questions about text using an LLM.

        Args:
            text: The input text or question
            conversation: Previous messages
              [{"role": "user"|"assistant", "content": "..."}]
            system_prompt: Instruction for the LLM
            model: OpenAI model name
            temperature: Creativity level

        Returns:
            LLM-generated response as string
        """

        if not self.client:
            raise OpenAIError(
                "OPENAI_API_KEY is missing. Cannot call OpenAI."
            )

        if not text or not text.strip():
            raise ValueError("Text to explain cannot be empty")

        if conversation is None:
            conversation = []

        messages = [
            {
                "role": "system",
                "content": system_prompt or self.DEFAULT_SYSTEM_PROMPT,
            }
        ]

        # Add previous conversation safely
        for msg in conversation:
            if "role" in msg and "content" in msg:
                messages.append(
                    {
                        "role": msg["role"],
                        "content": msg["content"],
                    }
                )

        # Current user input
        messages.append(
            {
                "role": "user",
                "content": text,
            }
        )

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )

            answer = response.choices[0].message.content.strip()
            logger.info("LLM response generated successfully")
            return answer

        except Exception as exc:
            logger.error(f"OpenAI API error: {exc}")
            raise
