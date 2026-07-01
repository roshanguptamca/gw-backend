import json
from abc import ABC, abstractmethod

from django.conf import settings

import requests


class BaseAIProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OpenAIProvider(BaseAIProvider):
    def __init__(self):
        from openai import OpenAI

        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OpenAI is not configured. Set OPENAI_API_KEY.")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""


class AzureOpenAIProvider(BaseAIProvider):
    def __init__(self):
        from openai import AzureOpenAI

        if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
            raise RuntimeError("Azure OpenAI is not configured. Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT.")
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""


class OllamaProvider(BaseAIProvider):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json={"model": settings.AI_MODEL, "system": system_prompt, "prompt": user_prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("response", "")


class GeminiProvider(BaseAIProvider):
    def __init__(self):
        from services.gemini import GeminiClient

        self.client = GeminiClient()
        if self.client.native is None and self.client.openai_style is None:
            raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY.")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        if self.client.native is not None:
            response = self.client.native.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[prompt],
            )
            return (response.text or "").strip()
        response = self.client.openai_style.chat.completions.create(
            model=settings.GEMINI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()


class DummyProvider(BaseAIProvider):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            payload = json.loads(user_prompt)
        except (TypeError, json.JSONDecodeError):
            payload = {"content": user_prompt}
        return json.dumps(
            {
                "optimized_resume": payload.get("resume", payload),
                "suggestions": [
                    "Use concise action verbs and quantify existing achievements "
                    "where the source already contains numbers."
                ],
                "confirmation_required_skills": payload.get("missing_skills", []),
            }
        )


def get_ai_provider() -> BaseAIProvider:
    providers = {
        "openai": OpenAIProvider,
        "azure_openai": AzureOpenAIProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
        "dummy": DummyProvider,
    }
    provider_class = providers.get(settings.AI_PROVIDER.lower())
    if not provider_class:
        raise ValueError(f"Unsupported AI_PROVIDER: {settings.AI_PROVIDER}")
    return provider_class()


def get_ai_providers():
    provider_names = [
        name.strip().casefold()
        for name in getattr(settings, "AI_PROVIDER_FALLBACKS", "gemini,openai").split(",")
        if name.strip()
    ]
    providers = []
    for name in provider_names:
        provider_class = {
            "openai": OpenAIProvider,
            "azure_openai": AzureOpenAIProvider,
            "gemini": GeminiProvider,
            "ollama": OllamaProvider,
        }.get(name)
        if not provider_class:
            continue
        try:
            providers.append((name, provider_class()))
        except Exception:
            continue
    return providers
