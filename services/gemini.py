import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Optional imports
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai
except ImportError:
    genai = None


class GeminiClient:
    """
    Production-ready Gemini LLM client.

    - Supports ANY document type (official, legal, school, medical, general letters)
    - English output by default
    - Optional preferred output language
    - Supports conversation history
    - Supports native Gemini SDK or OpenAI-compatible endpoint
    - No Django / S3 dependency
    """

    DEFAULT_SYSTEM_PROMPT = (
        "You are an assistant that explains ANY type of document "
        "(government, school, legal, medical, immigration, benefits, or general letters) "
        "in simple, clear, and practical language.\n\n"
        "Rules:\n"
        "- Summarize the key message\n"
        "- Explain what it means for the person\n"
        "- Clearly state what they should do next (if anything)\n"
        "- Avoid unnecessary background or definitions\n"
        "- Be concise and helpful\n"
    )

    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        if not self.gemini_key:
            logger.warning("GEMINI_API_KEY not set. GeminiClient disabled.")
            self.openai_style = None
            self.native = None
            return

        # OpenAI-compatible Gemini client
        self.openai_style = None
        if OpenAI is not None:
            try:
                self.openai_style = OpenAI(
                    api_key=self.gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
                logger.info("Gemini OpenAI-style client initialized.")
            except Exception as e:
                logger.warning(f"Gemini OpenAI-style init failed: {e}")

        # Native Gemini client
        self.native = None
        if genai is not None:
            try:
                self.native = genai.Client(api_key=self.gemini_key)
                logger.info("Gemini native client initialized.")
            except Exception as e:
                logger.warning(f"Gemini native init failed: {e}")

    def explain_text(
        self,
        text: str,
        conversation: Optional[List[dict]] = None,
        preferred_language: str = "English",
        system_prompt: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        engine: str = "native",  # "native" or "openai"
    ) -> str:
        """
        Explain a text snippet using Gemini.

        Args:
            text: Text to explain
            conversation: Optional previous messages [{"role":"user","content":"..."}]
            preferred_language: Output language (default: English)
            system_prompt: Optional custom system prompt
            model: Gemini model
            engine: "native" or "openai"

        Returns:
            Explanation string
        """
        if not text or len(text.strip()) < 5:
            raise ValueError("Text must be meaningful")

        conversation = conversation or []

        final_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        final_prompt += f"\n\nOutput language: {preferred_language}."

        if engine == "openai" and self.openai_style:
            return self._call_openai(
                text=text,
                conversation=conversation,
                system_prompt=final_prompt,
                model=model,
            )

        if engine == "native" and self.native:
            return self._call_native(
                text=text,
                system_prompt=final_prompt,
                model=model,
            )

        raise RuntimeError("No valid Gemini client available.")

    # ----------------------------
    # Internal methods
    # ----------------------------

    def _call_openai(self, text, conversation, system_prompt, model):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append(
            {
                "role": "user",
                "content": f"Explain the following document:\n{text}",
            }
        )

        try:
            response = self.openai_style.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Gemini OpenAI-style call failed: {e}")
            raise

    def _call_native(self, text, system_prompt, model):
        try:
            response = self.native.models.generate_content(
                model=model,
                contents=[
                    f"{system_prompt}\n\nExplain the following document:\n{text}"
                ],
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini native call failed: {e}")
            raise
