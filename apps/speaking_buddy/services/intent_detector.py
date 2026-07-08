"""Lightweight, dependency-free intent detection for AI Buddy conversations.

Currently focused on detecting "goodbye" intent across the languages the
Speaking Buddy commonly supports, so that a call/session can be ended
automatically as soon as the learner signs off - without waiting on a slow
round trip to an LLM.
"""

import re
import unicodedata

# Phrases are grouped by language purely for readability/maintenance; matching
# itself is language-agnostic (we just check whether any normalized phrase is
# contained in the normalized user text).
GOODBYE_PHRASES = {
    "en": [
        "bye", "bye bye", "goodbye", "good bye", "see you", "see ya",
        "see you later", "see you soon", "talk later", "talk to you later",
        "good night", "take care", "farewell", "catch you later",
        "i have to go", "i gotta go", "gotta go", "i'm off", "im off",
        "signing off", "have a good one",
    ],
    "nl": [
        "doei", "doeg", "dag", "tot ziens", "tot later", "tot straks",
        "welterusten", "de groetjes", "bedankt doei", "houdoe", "later",
    ],
    "hi": [
        "अलविदा", "फिर मिलेंगे", "फिर मिलते हैं", "नमस्ते", "टाटा",
        "चलता हूँ", "चलती हूँ", "अच्छा बाय",
    ],
    "fr": [
        "au revoir", "à bientôt", "a bientot", "à plus tard", "a plus tard",
        "bonne nuit", "adieu", "salut",
    ],
    "es": [
        "adiós", "adios", "hasta luego", "hasta la vista", "hasta pronto",
        "buenas noches", "nos vemos", "chao",
    ],
    "de": [
        "tschüss", "tschuss", "auf wiedersehen", "bis später", "bis spater",
        "gute nacht", "man sieht sich",
    ],
    "it": [
        "ciao", "arrivederci", "a dopo", "buonanotte", "ci vediamo",
    ],
    "other": [
        "namaste", "sayonara", "zai jian", "再见", "shalom",
    ],
}

# Sentences that imply the learner is wrapping up even without an exact
# farewell word (used as a soft fallback signal, not a hard match).
LEAVE_TAKING_HINTS = (
    "have to go", "gotta go", "i am off", "i'm off", "im off",
    "signing off", "let's stop", "lets stop", "stop the call", "end the call",
    "end call", "hang up", "moet gaan", "ik moet gaan", "मुझे जाना है",
)


def _flatten_phrases():
    flat = set()
    for phrases in GOODBYE_PHRASES.values():
        for phrase in phrases:
            flat.add(phrase.lower())
    # Longest phrases first so multi-word phrases are checked before short
    # substrings that could otherwise match too eagerly.
    return sorted(flat, key=len, reverse=True)


_FLAT_GOODBYE_PHRASES = _flatten_phrases()


class BuddyIntentDetector:
    """Detects simple conversational intents (currently: goodbye)."""

    @staticmethod
    def normalize(text):
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", text)
        text = text.strip().lower()
        # Strip common punctuation but keep unicode letters (incl. Devanagari)
        text = re.sub(r"[.,!?;:()\"'`]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def is_goodbye(cls, text):
        """Return True if the given text expresses a farewell/goodbye intent."""
        normalized = cls.normalize(text)
        if not normalized:
            return False

        for phrase in _FLAT_GOODBYE_PHRASES:
            phrase_norm = cls.normalize(phrase)
            if not phrase_norm:
                continue
            if cls._phrase_matches(phrase_norm, normalized):
                return True

        return cls._fallback_classify(normalized)

    @staticmethod
    def _phrase_matches(phrase_norm, normalized_text):
        if " " in phrase_norm:
            return phrase_norm in normalized_text
        # Single-word phrases: match as a whole word to avoid false positives
        # (e.g. "dag" inside "vandaag").
        return re.search(rf"(?:^|\s){re.escape(phrase_norm)}(?:$|\s)", normalized_text) is not None

    @classmethod
    def _fallback_classify(cls, normalized_text):
        """Heuristic fallback for farewells that don't use an exact phrase
        from the list above, e.g. "I have to go now, thanks for chatting"."""
        if len(normalized_text) > 80:
            # Long sentences are unlikely to be a simple goodbye; avoid
            # false positives on unrelated text that happens to mention e.g.
            # "go" somewhere in the middle.
            return False
        return any(hint in normalized_text for hint in LEAVE_TAKING_HINTS)

    @classmethod
    def detect(cls, text):
        return {"is_goodbye": cls.is_goodbye(text), "text": text}
