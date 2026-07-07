"""Single source of truth mapping voice_gender/voice_age preferences to a concrete
OpenAI Realtime voice name.

The mapping is intentionally a plain dict lookup so it is deterministic/stable:
the same (gender, age) pair always resolves to the same voice. This keeps the
voice fixed and predictable instead of "randomly" switching between male and
female voices for the same settings.
"""

# female -> nova/shimmer (never alloy), male -> onyx/echo, neutral -> alloy.
# IMPORTANT: alloy must never be used for female or male — it reads as a
# neutral/male-leaning voice on the Realtime API, which was the root cause of
# "Female gender selected but the call still sounds male".
VOICE_BY_GENDER_AGE = {
    ("female", "young"): "shimmer",
    ("female", "adult"): "nova",
    ("female", "senior"): "nova",
    ("male", "young"): "echo",
    ("male", "adult"): "echo",
    ("male", "senior"): "onyx",
    ("neutral", "young"): "alloy",
    ("neutral", "adult"): "alloy",
    ("neutral", "senior"): "alloy",
}

DEFAULT_VOICE = "alloy"


def resolve_voice(voice_gender: str | None, voice_age: str | None) -> str:
    """Return the OpenAI voice for a given gender/age preference.

    Falls back to the "adult" voice for the same gender if the age isn't
    recognized, and finally to DEFAULT_VOICE if the gender isn't recognized.
    """
    gender = (voice_gender or "neutral").lower()
    age = (voice_age or "adult").lower()
    return VOICE_BY_GENDER_AGE.get((gender, age)) or VOICE_BY_GENDER_AGE.get((gender, "adult")) or DEFAULT_VOICE
