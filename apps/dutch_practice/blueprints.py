"""Verified structures, not official questions or validated pass predictions."""

BANK_VERSION = "exam-bank-2026-10-v1"
SET_COUNT = 20
REFERENCE_DATE = "2026-10-04"
REFERENCES = [
    "https://www.inburgeren.nl/examen-doen/oefenen.jsp",
    "https://www.inburgeren.nl/examen-doen/inhoud-taalexamens-a2-b1-b2.jsp",
    "https://www.inburgeren.nl/examen-doen/inhoud-kennisexamens.jsp",
    "https://www.staatsexamensnt2.nl/voorbereiden/hoe-ziet-het-examen-eruit",
    "https://zoek.officielebekendmakingen.nl/stcrt-2024-15802.html",
]
KNM_TOPICS = {
    theme: 5
    for theme in (
        "werk_inkomen",
        "omgang_waarden_normen",
        "wonen",
        "gezondheid_zorg",
        "geschiedenis_geografie",
        "instanties",
        "staatsinrichting_rechtsstaat",
        "onderwijs_opvoeding",
    )
}


def blueprint(level, skill):
    if skill == "knm":
        if level != "A2":
            return None
        return {
            "family": "KNM",
            "label": "KNM · standalone civic component",
            "count": 40,
            "minutes": 45,
            "mix": {"civic_scenario": 40},
            "groups": 8,
            "topics": KNM_TOPICS,
            "playback": "replay",
            "limitations": "Original audio/text scenarios; official audiovisual presentation is not reproduced.",
        }
    if level == "A1":
        count = {"reading": 12, "listening": 12, "writing": 4, "speaking": 8}[skill]
        return {
            "family": "level_practice",
            "label": "A1 · extended level-based practice (not an official exam)",
            "count": count,
            "minutes": {"reading": 25, "listening": 25, "writing": 25, "speaking": 15}[skill],
            "mix": {
                {"reading": "reading", "listening": "listening", "writing": "practical", "speaking": "short"}[
                    skill
                ]: count
            },
            "groups": 4 if skill in ("reading", "listening") else count,
            "playback": "replay",
            "limitations": "Author-chosen length and timing; no applicable official A1 format verified.",
        }
    if level == "A2":
        count = {"reading": 25, "listening": 25, "writing": 4, "speaking": 16}[skill]
        return {
            "family": "inburgering",
            "label": "A2 · inburgering-style mock",
            "count": count,
            "minutes": {"reading": 65, "listening": 45, "writing": 40, "speaking": 35}[skill],
            "mix": (
                {"message": 2, "form": 2}
                if skill == "writing"
                else (
                    {"video_prompt": 4, "one_picture": 4, "two_pictures": 4, "three_pictures": 4}
                    if skill == "speaking"
                    else {skill: count}
                )
            ),
            "groups": 5 if skill in ("reading", "listening") else count,
            "playback": "replay",
            "limitations": (
                "A2 speaking uses original illustrated videos and diagrams, not official footage/pictures; "
                "four tasks per prompt type is an author-chosen balance, not a verified official weighting. "
                "A2 writing is officially pen-and-paper; this interface uses typed responses. "
                "Reading/listening counts follow the current DUO sample introductions, not a guarantee for every live paper."
            ),
        }
    if level not in ("B1", "B2"):
        return None
    mixes = {
        "B1": {
            "reading": {"reading": 36},
            "listening": {"listening": 38, "video_listening": 2},
            "writing": {"sentence": 8, "partial": 2, "short_text": 2},
            "speaking": {"short": 8, "medium": 8},
        },
        "B2": {
            "reading": {"reading": 36},
            "listening": {"listening": 38, "video_listening": 2},
            "writing": {"sentence": 8, "short_text": 1, "medium_text": 1},
            "speaking": {"short": 4, "medium": 8, "long": 1},
        },
    }
    mix = mixes[level][skill]
    return {
        "family": "nt2",
        "label": f"NT2 Programme {'I' if level == 'B1' else 'II'} · {level}",
        "count": sum(mix.values()),
        "minutes": {"reading": 110 if level == "B1" else 100, "listening": 90, "writing": 100, "speaking": 25}[skill],
        "mix": mix,
        "groups": 6 if skill == "reading" else 7 if skill == "listening" else sum(mix.values()),
        "playback": "once" if skill == "listening" else "replay",
        "preview_seconds": 25 if skill == "listening" else 0,
        "limitations": (
            "NT2 listening has approximately 40 tasks; this mock fixes 40 with two original illustrated clips. "
            "Synthetic audio lacks the variety of natural voices/accents in the real exam. Reading texts are on screen "
            "instead of in a printed booklet. B2 writing selects one valid mix within the official ranges. "
            "Speaking preparation times are practice choices; only response times are verified. "
            "NT2 gives approximately 25 minutes for speaking; DUO's overview says approximately 30 minutes."
        ),
    }


def catalog_formats():
    return [
        {"level": level, "skill": skill, **blueprint(level, skill)}
        for level in ("A1", "A2", "B1", "B2")
        for skill in ("reading", "listening", "writing", "speaking", "knm")
        if blueprint(level, skill) is not None
    ]
