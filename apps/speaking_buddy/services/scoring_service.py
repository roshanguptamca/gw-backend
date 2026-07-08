"""Analyze a finished BuddySession transcript and produce coaching scores.

Uses OpenAI when available. Falls back to a simple heuristic scorer based on
session length, word count, and detected corrections so a report can always
be generated even if OpenAI is unavailable or errors out.
"""

import json
import logging

from django.conf import settings

from openai import OpenAI

from .context_builder import BuddyContext

logger = logging.getLogger(__name__)

REQUIRED_SCORE_FIELDS = [
    "overall_score",
    "fluency_score",
    "grammar_score",
    "vocabulary_score",
    "confidence_score",
    "completeness_score",
]


def _client():
    if not settings.OPENAI_API_KEY:
        return None
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _clamp_score(value, default=50):
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = default
    return max(0, min(100, score))


def _transcript_text(transcript):
    return " ".join(str(item.get("text", "")) for item in transcript if isinstance(item, dict))


def _fallback_scores(transcript, session_summary=None):
    """Simple heuristic scoring used when OpenAI analysis is unavailable."""
    user_turns = [item for item in transcript if isinstance(item, dict) and item.get("role") == "user"]
    word_counts = [len(str(item.get("text", "")).split()) for item in user_turns]
    total_words = sum(word_counts)
    avg_words = (total_words / len(word_counts)) if word_counts else 0
    turn_count = len(user_turns)

    mistakes = (session_summary or {}).get("mistakes", []) if session_summary else []
    mistake_count = len(mistakes) if isinstance(mistakes, list) else 0

    # Simple heuristics: more turns and longer responses -> higher fluency/completeness.
    fluency = _clamp_score(40 + min(turn_count, 10) * 3 + min(avg_words, 15) * 1.5)
    completeness = _clamp_score(35 + min(turn_count, 12) * 4)
    grammar = _clamp_score(80 - mistake_count * 6)
    vocabulary = _clamp_score(45 + min(total_words, 200) / 4)
    confidence = _clamp_score((fluency + completeness) / 2)
    overall = _clamp_score((fluency + grammar + vocabulary + confidence + completeness) / 5)

    strengths = []
    if turn_count >= 4:
        strengths.append("You kept the conversation going with several responses.")
    if avg_words >= 6:
        strengths.append("Your responses had good length and detail.")
    if mistake_count == 0:
        strengths.append("No major grammar mistakes were detected.")
    if not strengths:
        strengths = ["You practiced speaking, which is the most important step."]

    improvements = []
    if avg_words < 6:
        improvements.append("Try giving longer, more detailed answers.")
    if mistake_count > 0:
        improvements.append("Review the corrected sentences from this session.")
    if turn_count < 4:
        improvements.append("Aim for a longer conversation next time to build fluency.")
    if not improvements:
        improvements = ["Keep practicing regularly to build more confidence."]

    return {
        "overall_score": overall,
        "fluency_score": fluency,
        "grammar_score": grammar,
        "vocabulary_score": vocabulary,
        "confidence_score": confidence,
        "completeness_score": completeness,
        "strengths": strengths[:3],
        "improvement_points": improvements[:3],
        "corrected_sentences": [
            {
                "original": item.get("original_text", ""),
                "corrected": item.get("corrected_text", ""),
                "explanation": item.get("explanation", ""),
            }
            for item in mistakes
            if isinstance(item, dict)
        ],
        "vocabulary_learned": (session_summary or {}).get("vocabulary", []) if session_summary else [],
        "next_practice_recommendation": "Practice a short scenario conversation to build on today's session.",
        "report_summary": (
            "Fallback report generated from session length and detected corrections "
            "because AI analysis was unavailable."
        ),
        "is_fallback": True,
    }


def analyze_session(context: BuddyContext, transcript: list, session_summary: dict | None = None) -> dict:
    """Return a coaching report dict for a finished session.

    Always returns a dict containing REQUIRED_SCORE_FIELDS plus strengths,
    improvement_points, corrected_sentences, vocabulary_learned,
    next_practice_recommendation, report_summary, and is_fallback.
    """
    client = _client()
    if client is None or not transcript:
        return _fallback_scores(transcript, session_summary)

    prompt = {
        "instruction": (
            "Analyze this language-practice conversation transcript and produce a coaching "
            "report as JSON. Score each field from 0-100. Be constructive and specific."
        ),
        "context": context.prompt_data if context else {},
        "transcript": transcript,
        "session_summary": session_summary or {},
        "required_fields": REQUIRED_SCORE_FIELDS
        + [
            "strengths",
            "improvement_points",
            "corrected_sentences",
            "vocabulary_learned",
            "next_practice_recommendation",
            "report_summary",
        ],
        "field_notes": {
            "strengths": "Array of exactly up to 3 short strings.",
            "improvement_points": "Array of exactly up to 3 short strings.",
            "corrected_sentences": "Array of {original, corrected, explanation} objects.",
            "vocabulary_learned": "Array of {word, translation, example_sentence} objects.",
            "next_practice_recommendation": "One short actionable sentence.",
            "report_summary": "A short paragraph summarizing the session performance.",
        },
    }
    try:
        response = client.chat.completions.create(
            model=getattr(settings, "SPEAKING_BUDDY_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (context.system_prompt if context else "")
                    + "\nYou are now acting as a speaking coach analyzing a finished session.",
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content)
        result = {field: _clamp_score(payload.get(field)) for field in REQUIRED_SCORE_FIELDS}
        result["strengths"] = list(payload.get("strengths") or [])[:3]
        result["improvement_points"] = list(payload.get("improvement_points") or [])[:3]
        result["corrected_sentences"] = payload.get("corrected_sentences") or []
        result["vocabulary_learned"] = payload.get("vocabulary_learned") or []
        result["next_practice_recommendation"] = payload.get("next_practice_recommendation", "")
        result["report_summary"] = payload.get("report_summary", "")
        result["is_fallback"] = False
        return result
    except Exception as exc:
        logger.warning("Speaking buddy scoring failed, using fallback: %s", exc)
        return _fallback_scores(transcript, session_summary)
