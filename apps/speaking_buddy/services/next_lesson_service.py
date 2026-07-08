"""Generate a personalized BuddyNextLesson from a session report."""

from ..models import BuddyNextLesson, BuddyScenario, BuddyWeakArea


def _recommend_scenarios(profile, focus_areas, limit=3):
    scenarios = BuddyScenario.objects.filter(language=profile.target_language, is_active=True)
    if getattr(profile, "buddy_settings", None) and profile.buddy_settings.kids_mode:
        scenarios = scenarios.filter(is_kids_safe=True)
    scenarios = scenarios.filter(level=profile.speaking_level) or scenarios
    picks = list(scenarios[:limit])
    return [
        {"id": scenario.id, "title": scenario.title, "slug": scenario.slug, "category": scenario.category}
        for scenario in picks
    ]


def generate_next_lesson(profile, session, report) -> BuddyNextLesson:
    """Build the next personalized lesson based on the latest report.

    Considers weak areas, mistakes made in the session, vocabulary learned,
    the user's learning goal, and their selected difficulty level.
    """
    weak_areas = list(
        BuddyWeakArea.objects.filter(profile=profile, language=session.language, status="active").order_by(
            "-severity", "-updated_at"
        )[:3]
    )
    focus_areas = [area.area_type for area in weak_areas] or list(report.improvement_points[:3])
    mistakes_to_fix = [
        {
            "original": item.get("original", item.get("original_text", "")),
            "corrected": item.get("corrected", item.get("corrected_text", "")),
        }
        for item in (report.corrected_sentences or [])
    ]
    vocabulary_to_review = report.vocabulary_learned or []
    recommended_scenarios = _recommend_scenarios(profile, focus_areas)

    title = f"Next practice: {', '.join(focus_areas[:2]) or 'general speaking'}"
    description = (
        report.next_practice_recommendation
        or f"Keep building on your last session by practicing {', '.join(focus_areas) or 'general conversation'}."
    )
    if profile.learning_goal:
        description += f" This supports your goal: {profile.learning_goal}."

    lesson = BuddyNextLesson.objects.create(
        user=profile.user,
        profile=profile,
        title=title,
        description=description,
        target_language=session.language,
        level=profile.speaking_level,
        focus_areas=focus_areas,
        recommended_scenarios=recommended_scenarios,
        vocabulary_to_review=vocabulary_to_review,
        mistakes_to_fix=mistakes_to_fix,
        status="pending",
        created_from_report=report,
    )
    return lesson
