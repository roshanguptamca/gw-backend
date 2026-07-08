"""Aggregate speaking-buddy progress stats for the /api/buddy/progress endpoint."""

from datetime import timedelta

from django.db.models import Avg
from django.utils import timezone

from ..models import BuddyNextLesson, BuddySession, BuddySessionReport, BuddyVocabulary, BuddyWeakArea

_SCORE_FIELDS = {
    "fluency": "fluency_score",
    "grammar": "grammar_score",
    "vocabulary": "vocabulary_score",
    "confidence": "confidence_score",
    "completeness": "completeness_score",
}


def _current_streak(session_dates):
    """Count consecutive days (including today or yesterday) with a session."""
    if not session_dates:
        return 0
    dates = sorted(set(session_dates), reverse=True)
    today = timezone.localdate()
    streak = 0
    expected = today
    for d in dates:
        if d == expected:
            streak += 1
            expected = expected - timedelta(days=1)
        elif d == expected + timedelta(days=1):
            continue
        else:
            break
    return streak


def get_progress(profile) -> dict:
    sessions = BuddySession.objects.filter(profile=profile, status="ended")
    reports = BuddySessionReport.objects.filter(session__profile=profile)
    total_conversations = sessions.count()
    total_minutes = round(sum(s.duration_seconds for s in sessions) / 60, 1)
    avg_scores = reports.aggregate(
        avg_overall=Avg("overall_score"),
        **{f"avg_{key}": Avg(field) for key, field in _SCORE_FIELDS.items()},
    )
    average_score = round(avg_scores.get("avg_overall") or 0, 1)

    ordered_reports = list(reports.order_by("created_at"))
    score_trend = [{"date": r.created_at.date().isoformat(), "overall_score": r.overall_score} for r in ordered_reports]

    skill_avgs = {key: round(avg_scores.get(f"avg_{key}") or 0, 1) for key in _SCORE_FIELDS}
    strongest_skill = max(skill_avgs, key=skill_avgs.get) if skill_avgs else None
    weakest_skill = min(skill_avgs, key=skill_avgs.get) if skill_avgs else None

    since = timezone.now() - timedelta(days=7)
    weekly_sessions = sessions.filter(started_at__gte=since)
    weekly_counts = {}
    for s in weekly_sessions:
        day = s.started_at.date().isoformat()
        weekly_counts[day] = weekly_counts.get(day, 0) + 1
    weekly_practice_chart = [{"date": day, "count": count} for day, count in sorted(weekly_counts.items())]

    session_dates = list(sessions.values_list("started_at__date", flat=True))
    streak = _current_streak(session_dates)

    vocabulary_learned = BuddyVocabulary.objects.filter(profile=profile).count()
    mistakes_reduced = 0
    if len(ordered_reports) >= 2:
        first_mistakes = len(ordered_reports[0].corrected_sentences or [])
        last_mistakes = len(ordered_reports[-1].corrected_sentences or [])
        mistakes_reduced = max(0, first_mistakes - last_mistakes)

    next_lesson = (
        BuddyNextLesson.objects.filter(user=profile.user, status__in=["pending", "started"])
        .order_by("-created_at")
        .first()
    )
    weak_areas = list(BuddyWeakArea.objects.filter(profile=profile, status="active").order_by("-severity")[:5])

    return {
        "total_conversations": total_conversations,
        "total_minutes_practiced": total_minutes,
        "average_score": average_score,
        "score_trend": score_trend,
        "weekly_practice_chart": weekly_practice_chart,
        "strongest_skill": strongest_skill,
        "weakest_skill": weakest_skill,
        "skill_averages": skill_avgs,
        "vocabulary_learned": vocabulary_learned,
        "mistakes_reduced": mistakes_reduced,
        "current_streak": streak,
        "next_recommended_lesson": (
            {
                "id": next_lesson.id,
                "title": next_lesson.title,
                "description": next_lesson.description,
                "status": next_lesson.status,
            }
            if next_lesson
            else None
        ),
        "weak_areas": [
            {
                "id": area.id,
                "area_type": area.area_type,
                "title": area.title,
                "severity": area.severity,
                "status": area.status,
            }
            for area in weak_areas
        ],
    }
