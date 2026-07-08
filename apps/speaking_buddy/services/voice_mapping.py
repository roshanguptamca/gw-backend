"""Single source of truth mapping voice_gender/voice_age/voice_style preferences
to a concrete, Realtime-API-supported OpenAI voice name.

The mapping is intentionally a plain dict lookup so it is deterministic/stable:
the same (gender, age/style) pair always resolves to the same voice. This keeps
the voice fixed and predictable instead of "randomly" switching between male
and female voices for the same settings.

IMPORTANT — Realtime voice support:
The OpenAI Realtime API only accepts a fixed set of voices. Sending an
unsupported voice (e.g. the older Chat/TTS-only voices "nova", "onyx",
"fable") makes token creation fail outright with a 400 error, which broke
production ("Invalid value: 'nova'. Supported values are: ..."). Every path
in this module must therefore only ever return a name from
SUPPORTED_REALTIME_VOICES.
"""

import logging

logger = logging.getLogger(__name__)

# The full, current set of voices the OpenAI Realtime API accepts. Keep this
# in sync with OpenAI's supported-voices list — if it changes again, update
# this set and the mappings below rather than passing arbitrary values through.
SUPPORTED_REALTIME_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
}

# Older Chat Completions/TTS-only voice names that must never be sent to the
# Realtime API. Kept explicit (rather than just "anything not supported")
# purely for clearer logging when one of these legacy values is encountered.
LEGACY_UNSUPPORTED_REALTIME_VOICES = {"nova", "onyx", "fable"}

DEFAULT_VOICE = "alloy"

# female -> shimmer (never alloy, never nova — nova is not Realtime-supported).
# male -> echo. neutral -> alloy.
# IMPORTANT: alloy must never be used for female or male — it reads as a
# neutral/male-leaning voice on the Realtime API, which was the root cause of
# "Female gender selected but the call still sounds male".
VOICE_BY_GENDER_AGE = {
    ("female", "young"): "shimmer",
    ("female", "adult"): "shimmer",
    ("female", "senior"): "coral",
    ("male", "young"): "echo",
    ("male", "adult"): "echo",
    ("male", "senior"): "ash",
    ("neutral", "young"): "alloy",
    ("neutral", "adult"): "alloy",
    ("neutral", "senior"): "alloy",
}

# gender + voice_style fallback mapping used by resolve_realtime_voice() when
# a requested voice is missing/unsupported and there is no usable
# (gender, age) preference to fall back on.
VOICE_BY_GENDER_STYLE = {
    ("female", "warm"): "coral",
    ("female", "calm"): "sage",
    ("female", "clear"): "shimmer",
    ("female", "energetic"): "shimmer",
    ("male", "warm"): "ash",
    ("male", "calm"): "echo",
    ("male", "clear"): "echo",
    ("male", "energetic"): "echo",
    ("neutral", "warm"): "alloy",
    ("neutral", "calm"): "alloy",
    ("neutral", "clear"): "alloy",
    ("neutral", "energetic"): "alloy",
}

# Plain gender fallback, used when style is missing/unrecognized too.
VOICE_BY_GENDER = {
    "female": "shimmer",
    "male": "echo",
    "neutral": "alloy",
}


def resolve_voice(voice_gender: str | None, voice_age: str | None) -> str:
    """Return the OpenAI Realtime voice for a given gender/age preference.

    Falls back to the "adult" voice for the same gender if the age isn't
    recognized, and finally to DEFAULT_VOICE if the gender isn't recognized.
    The result is always a member of SUPPORTED_REALTIME_VOICES.
    """
    gender = (voice_gender or "neutral").lower()
    age = (voice_age or "adult").lower()
    return VOICE_BY_GENDER_AGE.get((gender, age)) or VOICE_BY_GENDER_AGE.get((gender, "adult")) or DEFAULT_VOICE


def resolve_realtime_voice(
    requested_voice: str | None,
    voice_gender: str | None = None,
    voice_style: str | None = None,
) -> str:
    """Safely resolve any requested voice into one the Realtime API supports.

    - If requested_voice is already Realtime-supported, use it as-is.
    - Otherwise (missing, unrecognized, or a legacy voice like "nova"/"onyx"/
      "fable"), log a warning and derive a supported voice from
      voice_gender/voice_style, finally falling back to DEFAULT_VOICE.
    - Never raises — this function must never be the reason token creation
      crashes.
    """
    requested = (requested_voice or "").strip().lower()
    gender = (voice_gender or "neutral").strip().lower()
    style = (voice_style or "").strip().lower()

    if requested in SUPPORTED_REALTIME_VOICES:
        return requested

    resolved = VOICE_BY_GENDER_STYLE.get((gender, style)) or VOICE_BY_GENDER.get(gender) or DEFAULT_VOICE
    logger.warning(
        "AI Buddy voice resolved: requested=%s gender=%s style=%s resolved=%s source=fallback_mapping",
        requested_voice,
        gender,
        style,
        resolved,
    )
    return resolved
