import json
import logging
import re

from apps.ai_services.providers import get_ai_providers

from .services import resume_snapshot

logger = logging.getLogger(__name__)


def generate_professional_summary(resume, job_title, language):
    snapshot = resume_snapshot(resume)
    facts = {
        "current_professional_title": snapshot["personal"].get("professional_title", ""),
        "skills": [item["name"] for item in snapshot["skills"] if item.get("name")][:12],
        "experience": [
            {
                "job_title": item.get("job_title", ""),
                "employer": item.get("employer", ""),
                "description": item.get("description", ""),
            }
            for item in snapshot["experiences"][:6]
        ],
        "education": [
            {
                "degree": item.get("degree", ""),
                "field_of_study": item.get("field_of_study", ""),
                "institution": item.get("institution", ""),
            }
            for item in snapshot["education"][:4]
        ],
        "projects": [
            {"name": item.get("name", ""), "description": item.get("description", "")}
            for item in snapshot["projects"][:4]
        ],
        "certifications": [item.get("name", "") for item in snapshot["certifications"][:6]],
    }
    system_prompt = (
        "Write a concise professional resume summary of 2 to 4 sentences. "
        "Use only facts explicitly supplied in the JSON. Do not invent years of experience, achievements, "
        "skills, employers, education, certifications, seniority, or metrics. "
        "The requested job title is a target role, not proof of past employment. "
        f"Write in {'Dutch' if language == 'nl' else 'English'}. Return plain text only."
    )
    user_prompt = json.dumps(
        {"target_job_title": job_title, "resume_facts": facts},
        ensure_ascii=False,
    )
    for provider_name, provider in get_ai_providers():
        try:
            summary = _clean_summary(provider.generate(system_prompt, user_prompt))
            if summary:
                return {"summary": summary, "provider": provider_name, "generated_by_ai": True}
        except Exception as exc:
            logger.warning("Summary generation with %s failed; trying fallback: %s", provider_name, exc)
    return {
        "summary": _fallback_summary(job_title, facts, language),
        "provider": "deterministic",
        "generated_by_ai": False,
    }


def generate_skill_suggestions(resume, job_title, language):
    snapshot = resume_snapshot(resume)
    existing = [item["name"] for item in snapshot["skills"] if item.get("name")]
    system_prompt = (
        "Suggest 6 to 10 common resume skills for the requested target job title. "
        "These are suggestions requiring user confirmation, not claims that the user has these skills. "
        "Return JSON only as an array of objects with keys name and category. "
        "Use one of these categories: Technical, Tool, Functional, Soft Skill, Methodology. "
        "Do not include skills already listed in existing_skills. "
        f"Use {'Dutch' if language == 'nl' else 'English'} names for non-technical skills."
    )
    user_prompt = json.dumps(
        {"target_job_title": job_title, "existing_skills": existing},
        ensure_ascii=False,
    )
    for provider_name, provider in get_ai_providers():
        try:
            suggestions = _clean_skill_suggestions(provider.generate(system_prompt, user_prompt), existing)
            if suggestions:
                return {
                    "skills": suggestions,
                    "provider": provider_name,
                    "generated_by_ai": True,
                }
        except Exception as exc:
            logger.warning("Skill generation with %s failed; trying fallback: %s", provider_name, exc)
    return {
        "skills": _fallback_skills(job_title, existing, language),
        "provider": "deterministic",
        "generated_by_ai": False,
    }


def _clean_summary(value):
    text = re.sub(r"^```(?:text)?\s*|\s*```$", "", (value or "").strip(), flags=re.I)
    return re.sub(r"\s+", " ", text)[:1500].strip()


def _clean_skill_suggestions(value, existing):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (value or "").strip(), flags=re.I)
    payload = json.loads(cleaned)
    if isinstance(payload, dict):
        payload = payload.get("skills", [])
    if not isinstance(payload, list):
        raise ValueError("AI skill generator did not return a list.")
    existing_names = {item.strip().casefold() for item in existing}
    categories = {"Technical", "Tool", "Functional", "Soft Skill", "Methodology"}
    suggestions = []
    seen = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = re.sub(r"\s+", " ", str(item.get("name", ""))).strip()[:120]
        normalized = name.casefold()
        if not name or normalized in existing_names or normalized in seen:
            continue
        category = item.get("category")
        suggestions.append(
            {
                "name": name,
                "category": category if category in categories else "Functional",
                "status": "needs_confirmation",
            }
        )
        seen.add(normalized)
        if len(suggestions) == 10:
            break
    return suggestions


def _fallback_summary(job_title, facts, language):
    skills = facts["skills"][:5]
    experience_titles = [item["job_title"] for item in facts["experience"] if item["job_title"]][:3]
    if language == "nl":
        parts = [f"Professional gericht op een functie als {job_title}."]
        if experience_titles:
            parts.append(f"Ervaring in functies als {', '.join(experience_titles)}.")
        if skills:
            parts.append(f"Vaardigheden: {', '.join(skills)}.")
        return " ".join(parts)
    parts = [f"Professional targeting a {job_title} role."]
    if experience_titles:
        parts.append(f"Experience includes roles such as {', '.join(experience_titles)}.")
    if skills:
        parts.append(f"Skills include {', '.join(skills)}.")
    return " ".join(parts)


def _fallback_skills(job_title, existing, language):
    title = job_title.casefold()
    groups = {
        "support": [
            ("Customer Service", "Functional"),
            ("Communication", "Soft Skill"),
            ("Problem Solving", "Soft Skill"),
            ("CRM", "Tool"),
            ("Ticket Management", "Tool"),
            ("Conflict Resolution", "Functional"),
        ],
        "developer": [
            ("Software Development", "Technical"),
            ("Git", "Tool"),
            ("REST API", "Technical"),
            ("Testing", "Technical"),
            ("Problem Solving", "Soft Skill"),
            ("Agile", "Methodology"),
        ],
        "manager": [
            ("Project Management", "Functional"),
            ("Leadership", "Soft Skill"),
            ("Stakeholder Management", "Soft Skill"),
            ("Communication", "Soft Skill"),
            ("Planning", "Functional"),
            ("Risk Management", "Functional"),
        ],
    }
    key = next((name for name in groups if name in title), "support")
    translations = {
        "Customer Service": "Klantenservice",
        "Communication": "Communicatie",
        "Problem Solving": "Probleemoplossend vermogen",
        "Ticket Management": "Ticketbeheer",
        "Conflict Resolution": "Conflictoplossing",
        "Software Development": "Softwareontwikkeling",
        "Testing": "Testen",
        "Project Management": "Projectmanagement",
        "Leadership": "Leiderschap",
        "Stakeholder Management": "Stakeholdermanagement",
        "Planning": "Planning",
        "Risk Management": "Risicomanagement",
    }
    existing_names = {item.casefold() for item in existing}
    return [
        {
            "name": translations.get(name, name) if language == "nl" else name,
            "category": category,
            "status": "needs_confirmation",
        }
        for name, category in groups[key]
        if name.casefold() not in existing_names
    ]
