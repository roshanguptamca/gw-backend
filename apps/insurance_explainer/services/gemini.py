"""Insurance-specific Gemini AI service (uses shared GeminiClient / google-genai SDK)."""

import json
import re
import logging
from services.gemini import GeminiClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert insurance policy analyst. Your job is to analyze insurance policy documents and explain them clearly to ordinary people.  # noqa: E501
When given a policy, you must:
1. Identify the type of insurance (health, car, home, travel, life, etc.)
2. Highlight what IS covered (green — nice to have)
3. Explain important clauses people must know (blue — important)
4. Identify what is MISSING or NOT covered (orange — gaps)
5. Flag risky clauses that could lead to claim rejection (red — risks)
6. Provide clear next action items

You are country-aware. Adjust explanations based on the country's insurance regulations:
- Netherlands: mention Dutch AFM/DNB regulations, Zorgverzekeringswet if health
- Germany: mention GKV/PKV distinction, VVG law if relevant
- France: mention assurance obligatoire vs complémentaire if relevant
- UK: mention FCA regulations, UK-specific terms
- US: mention state-specific rules, ACA if health insurance
- EU generally: reference EIOPA guidelines if applicable
- Other: use general international best practices

Always respond in the language specified by the user.

Return your response as a JSON object with this exact structure:
{
  "insurance_type": "detected type of insurance",
  "summary": "2-3 sentence plain language summary",
  "coverage_highlights": [
    {"title": "short title", "detail": "explanation"}
  ],
  "important_clauses": [
    {"title": "short title", "detail": "explanation"}
  ],
  "missing_coverage": [
    {"title": "short title", "detail": "explanation"}
  ],
  "risks": [
    {"title": "short title", "detail": "explanation"}
  ],
  "action_items": [
    "Action item 1",
    "Action item 2"
  ],
  "overall_score": "good|fair|poor",
  "score_reason": "one sentence explaining the overall score"
}

Return ONLY valid JSON, no markdown code fences, no extra text."""


class InsuranceGeminiService:
    """Calls Gemini to analyse insurance policy text. Uses shared GeminiClient (google-genai SDK)."""

    def __init__(self):
        self._client = GeminiClient()
        if self._client.native is None and self._client.openai_style is None:
            logger.error("InsuranceGeminiService: no Gemini client available. Check GEMINI_API_KEY.")

    @property
    def _available(self) -> bool:
        return self._client.native is not None or self._client.openai_style is not None

    def _generate(self, prompt: str) -> str:
        """Call Gemini with a single prompt, trying native then openai-style."""
        if self._client.native is not None:
            try:
                response = self._client.native.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[prompt],
                )
                return response.text.strip()
            except Exception as e:
                logger.warning("Insurance native Gemini call failed: %s", e)

        if self._client.openai_style is not None:
            try:
                resp = self._client.openai_style.chat.completions.create(
                    model="gemini-2.0-flash",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("Insurance openai-style Gemini call failed: %s", e)

        raise RuntimeError("No Gemini client available.")

    def analyse_policy(self, policy_text: str, country: str, language: str, provider_url: str = "") -> dict:
        """Run full structured analysis of a policy document."""
        if not self._available:
            raise RuntimeError("Gemini model not available. Check GEMINI_API_KEY.")

        context_parts = [f"Country: {country}", f"Response language: {language}"]
        if provider_url:
            context_parts.append(f"Provider URL: {provider_url}")

        prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            "Context:\n" + "\n".join(context_parts) + "\n\n"
            f"Insurance policy text:\n{policy_text[:15000]}"
        )

        raw = self._generate(prompt)

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Gemini returned non-JSON for insurance analysis; wrapping as summary.")
            return {
                "insurance_type": "Unknown",
                "summary": raw[:500],
                "coverage_highlights": [],
                "important_clauses": [],
                "missing_coverage": [],
                "risks": [],
                "action_items": [],
                "overall_score": "fair",
                "score_reason": "Analysis completed but structured output was not available.",
            }

    def chat(self, policy_text: str, analysis: dict, history: list, question: str, country: str, language: str) -> str:
        """Answer a follow-up question about the policy."""
        if not self._available:
            raise RuntimeError("Gemini model not available.")

        analysis_summary = json.dumps(analysis, ensure_ascii=False)[:3000] if analysis else ""

        system = (
            f"You are an insurance expert assistant. "
            f"You have already analysed an insurance policy for a user in {country}. "
            f"Always respond in {language}. "
            f"Be concise, practical, and friendly. "
            f"Here is the analysis you produced:\n{analysis_summary}\n\n"
            f"Policy text (truncated):\n{policy_text[:5000]}"
        )

        turns = []
        for msg in history[-10:]:
            turns.append(f"{msg['role'].upper()}: {msg['content']}")
        turns.append(f"USER: {question}")

        prompt = f"{system}\n\nConversation:\n" + "\n".join(turns) + "\n\nASSISTANT:"
        return self._generate(prompt)
