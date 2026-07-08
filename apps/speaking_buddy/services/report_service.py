"""Generate and persist BuddySessionReport objects from finished sessions."""

from django.utils import timezone

from ..models import BuddySessionReport, BuddyWeakArea
from .scoring_service import analyze_session


def generate_report(session, context, transcript, session_summary=None) -> BuddySessionReport:
    """Create or refresh the BuddySessionReport for a finished BuddySession."""
    analysis = analyze_session(context, transcript, session_summary)
    report, _created = BuddySessionReport.objects.update_or_create(
        session=session,
        defaults={
            "user": session.profile.user,
            "overall_score": analysis["overall_score"],
            "fluency_score": analysis["fluency_score"],
            "grammar_score": analysis["grammar_score"],
            "vocabulary_score": analysis["vocabulary_score"],
            "confidence_score": analysis["confidence_score"],
            "completeness_score": analysis["completeness_score"],
            "strengths": analysis["strengths"],
            "improvement_points": analysis["improvement_points"],
            "corrected_sentences": analysis["corrected_sentences"],
            "vocabulary_learned": analysis["vocabulary_learned"],
            "next_practice_recommendation": analysis["next_practice_recommendation"],
            "report_summary": analysis["report_summary"],
            "is_fallback": analysis.get("is_fallback", False),
        },
    )
    return report


_SCORE_TO_AREA_TYPE = {
    "grammar_score": "grammar",
    "vocabulary_score": "vocabulary",
    "fluency_score": "fluency",
    "confidence_score": "confidence",
}

_LOW_THRESHOLD = 55
_MEDIUM_THRESHOLD = 70


def _severity_for_score(score):
    if score < _LOW_THRESHOLD:
        return "high"
    if score < _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def update_weak_areas(profile, session, report: BuddySessionReport):
    """Create/update BuddyWeakArea rows based on the latest session report.

    Any score below the "good" threshold generates or refreshes a weak area
    record so the learner has a clear, evolving list of what to work on.
    """
    now = timezone.now()
    language = session.language
    for score_field, area_type in _SCORE_TO_AREA_TYPE.items():
        score = getattr(report, score_field, 100)
        if score >= _MEDIUM_THRESHOLD:
            # Mark existing weak areas of this type as improving/resolved.
            BuddyWeakArea.objects.filter(
                profile=profile, area_type=area_type, language=language, status="active"
            ).update(status="improving" if score < 85 else "resolved", last_seen_at=now)
            continue

        severity = _severity_for_score(score)
        title = f"{area_type.capitalize()} needs practice"
        evidence = list(report.improvement_points or [])[:3]
        weak_area, _created = BuddyWeakArea.objects.update_or_create(
            profile=profile,
            area_type=area_type,
            title=title,
            language=language,
            defaults={
                "user": profile.user,
                "description": f"Recent score: {score}/100.",
                "severity": severity,
                "evidence": evidence,
                "improvement_plan": report.next_practice_recommendation or "",
                "status": "active",
                "last_seen_at": now,
            },
        )
    return BuddyWeakArea.objects.filter(profile=profile, language=language)
