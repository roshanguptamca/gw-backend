import ipaddress
import json
import re
import socket
from datetime import timedelta
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

import requests

from apps.jobs.models import ATSReport, JobMatch, TemporaryJobDescription
from apps.resumes.models import OptimizedResume, TemporaryGeneratedResume
from apps.resumes.services import create_resume_from_snapshot, keyword_counts, resume_snapshot


SKILL_ALIASES = {
    "agile": "Agile",
    "angular": "Angular",
    "api": "API Design",
    "apis": "API Design",
    "aws": "AWS",
    "ci/cd": "CI/CD",
    "cloud": "Cloud Architecture",
    "data governance": "Data Governance",
    "design patterns": "Design Patterns",
    "devops": "DevOps",
    "docker": "Docker",
    "hexagonal architecture": "Hexagonal Architecture",
    "hexagonale architectuur": "Hexagonal Architecture",
    "kafka": "Kafka",
    "kubernetes": "Kubernetes",
    "microservices": "Microservices",
    "nestjs": "NestJS",
    "nest.js": "NestJS",
    "nosql": "NoSQL",
    "postgresql": "PostgreSQL",
    "sap": "SAP",
    "s4/hana": "SAP S/4HANA",
    "s/4hana": "SAP S/4HANA",
    "security": "Security",
    "snowflake": "Snowflake",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    "test driven development": "Test Driven Development",
    "tdd": "Test Driven Development",
    "time-series": "Time-Series Databases",
    "typescript": "TypeScript",
    "communication": "communication",
    "communicatie": "communication",
    "leadership": "leadership",
    "leiderschap": "leadership",
    "project management": "project management",
    "projectmanagement": "project management",
    "stakeholder management": "stakeholder management",
    "stakeholdermanagement": "stakeholder management",
    "customer service": "customer service",
    "klantenservice": "customer service",
    "sales": "sales",
    "verkoop": "sales",
    "accounting": "accounting",
    "boekhouding": "accounting",
    "data analysis": "data analysis",
    "data-analyse": "data analysis",
    "software development": "software development",
    "softwareontwikkeling": "software development",
}

SKILL_CANONICAL = {value.casefold(): value.casefold() for value in SKILL_ALIASES.values()}
SKILL_CANONICAL.update({alias.casefold(): value.casefold() for alias, value in SKILL_ALIASES.items()})

REPORT_TEXT = {
    "en": {
        "has_contact_details": "Add complete contact details.",
        "has_summary": "Add a professional summary.",
        "has_experience": "Add work experience.",
        "has_education": "Add education.",
        "has_three_skills": "Add at least three relevant skills.",
    },
    "nl": {
        "has_contact_details": "Voeg volledige contactgegevens toe.",
        "has_summary": "Voeg een professioneel profiel toe.",
        "has_experience": "Voeg werkervaring toe.",
        "has_education": "Voeg een opleiding toe.",
        "has_three_skills": "Voeg minimaal drie relevante vaardigheden toe.",
    },
}


def canonical_skill(value):
    normalized = re.sub(r"\s+", " ", value.strip()).casefold()
    return SKILL_CANONICAL.get(normalized, normalized)


def extract_known_skills(text):
    normalized = text.casefold()
    matches = []
    for alias, label in SKILL_ALIASES.items():
        if re.search(rf"(?<![\w+]){re.escape(alias)}(?![\w+])", normalized) and label not in matches:
            matches.append(label)
    return matches


def parse_job_text(text):
    clean = re.sub(r"\s+", " ", text).strip()
    counts = keyword_counts(clean)
    skills = extract_known_skills(clean)
    title_match = re.search(r"(?:job title|position|role|functietitel|functie)\s*[:\-]\s*([^.;\n]+)", text, re.I)
    required_pattern = (
        r"(?:required skills|required qualifications|requirements|vereiste vaardigheden|vereisten)\s*[:\-]\s*"
        r"(.+?)(?=(?:preferred|pré|responsibilities|verantwoordelijkheden|education|opleiding|$))"
    )
    required_match = re.search(
        required_pattern,
        clean,
        re.I,
    )
    preferred_pattern = (
        r"(?:preferred skills|preferred qualifications|nice to have|pré|voorkeur)\s*[:\-]\s*"
        r"(.+?)(?=(?:responsibilities|verantwoordelijkheden|education|opleiding|$))"
    )
    preferred_match = re.search(
        preferred_pattern,
        clean,
        re.I,
    )
    responsibilities_match = re.search(
        r"(?:responsibilities|what you will do|duties|verantwoordelijkheden|werkzaamheden)\s*[:\-]\s*(.+?)(?=(?:requirements|vereisten|education|opleiding|$))",
        clean,
        re.I,
    )
    education = re.findall(r"(?:bachelor|master|phd|degree|opleiding|diploma)[^.;]{0,100}", clean, re.I)
    certifications = re.findall(r"(?:certification|certified|certificaat|gecertificeerd)[^.;]{0,100}", clean, re.I)
    required_skills = extract_known_skills(required_match.group(1)) if required_match else skills
    preferred_skills = _split_requirements(preferred_match.group(1)) if preferred_match else []
    responsibilities = _split_requirements(responsibilities_match.group(1)) if responsibilities_match else []
    return {
        "title": title_match.group(1).strip() if title_match else "",
        "skills": skills,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "responsibilities": responsibilities,
        "education": education,
        "certifications": certifications,
        "keywords": [word for word, _ in counts.most_common(50)],
        "raw_text": clean,
    }


def _split_requirements(value):
    return [item.strip(" -•") for item in re.split(r"[,;|•]", value) if item.strip(" -•")][:30]


def parse_job_url(url):
    current_url = url
    for _ in range(6):
        parsed_url = urlparse(current_url)
        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS job URLs are supported.")
        _validate_public_url(parsed_url)
        response = requests.get(
            current_url,
            timeout=12,
            headers={"User-Agent": "GuideWisey Career Suite/1.0"},
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                raise ValueError("The job URL returned an invalid redirect.")
            current_url = urljoin(current_url, location)
            continue
        response.raise_for_status()
        break
    else:
        raise ValueError("The job URL redirected too many times.")
    if len(response.content) > 5 * 1024 * 1024:
        raise ValueError("Job page is too large.")
    try:
        import trafilatura

        text = trafilatura.extract(response.text, include_links=False, include_images=False)
    except ImportError:
        text = None
    if not text:
        try:
            from bs4 import BeautifulSoup

            text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", response.text)
    if not text or not text.strip():
        raise ValueError("The job page did not contain readable text.")
    parsed = parse_job_text(text or "")
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "html.parser")
        metadata = _job_metadata(soup)
        parsed["title"] = metadata["title"] or parsed["title"]
        parsed["company"] = metadata["company"]
        parsed["location"] = metadata["location"]
    except ImportError:
        parsed["company"] = ""
        parsed["location"] = ""
    return parsed


def _job_metadata(soup):
    metadata = _json_ld_job_metadata(soup)
    if metadata["title"]:
        return metadata
    open_graph_title = _meta_content(soup, "meta[property='og:title']", "meta[name='twitter:title']")
    linkedin_match = re.match(
        r"^(?P<company>.+?) hiring (?P<title>.+?) in (?P<location>.+?)\s*\|\s*LinkedIn$",
        open_graph_title,
        re.I,
    )
    if linkedin_match:
        return {key: value.strip() for key, value in linkedin_match.groupdict().items()}
    return {
        "title": open_graph_title,
        "company": _meta_content(soup, "meta[property='og:site_name']", "meta[name='author']"),
        "location": _find_location(soup),
    }


def _json_ld_job_metadata(soup):
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
            nodes.extend(payload["@graph"])
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") != "JobPosting":
                continue
            organization = node.get("hiringOrganization") or {}
            location = node.get("jobLocation") or {}
            if isinstance(location, list):
                location = location[0] if location else {}
            address = location.get("address") or {}
            location_label = ", ".join(
                str(address.get(key, "")).strip()
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if address.get(key)
            )
            return {
                "title": str(node.get("title", "")).strip(),
                "company": str(organization.get("name", "")).strip(),
                "location": location_label,
            }
    return {"title": "", "company": "", "location": ""}


def _meta_content(soup, *selectors):
    for selector in selectors:
        element = soup.select_one(selector)
        if element and element.get("content"):
            return element["content"].strip()
    return ""


def _find_location(soup):
    location = soup.select_one("[itemprop='jobLocation'], [itemprop='addressLocality']")
    return location.get_text(" ", strip=True) if location else ""


def _validate_public_url(parsed_url):
    if not parsed_url.hostname:
        raise ValueError("The job URL must include a valid hostname.")
    try:
        addresses = socket.getaddrinfo(parsed_url.hostname, parsed_url.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("The job URL hostname could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private, local, and reserved network addresses are not allowed.")


def store_temporary_job(user, parsed, source_url="", anonymous_identity=None):
    return TemporaryJobDescription.objects.create(
        user=user,
        anonymous_identity=anonymous_identity,
        raw_text=parsed.get("raw_text", ""),
        parsed_json=parsed,
        source_url=source_url,
        expires_at=timezone.now() + timedelta(hours=settings.CAREER_SUITE_TEMP_TTL_HOURS),
    )


def _ratio(matched, total):
    return round((len(matched) / max(len(total), 1)) * 100, 2)


def analyze_match(resume, job_description, user, report_language=None):
    report_language = report_language or resume.locale
    snapshot = resume_snapshot(resume)
    resume_text = json.dumps(snapshot, default=str)
    resume_words = set(keyword_counts(resume_text))
    job_words = set(job_description.parsed_json.get("keywords") or keyword_counts(job_description.raw_text))
    job_skills = set(
        canonical_skill(word)
        for word in (
            job_description.parsed_json.get("required_skills") or job_description.parsed_json.get("skills", [])
        )
    )
    resume_skills = {canonical_skill(item["name"]) for item in snapshot["skills"]}
    matched_skills = sorted(job_skills & resume_skills)
    matched_keywords = sorted(job_words & resume_words)
    skills_score = _ratio(matched_skills, job_skills)
    keyword_score = _ratio(matched_keywords, job_words)
    experience_score = min(100, len(snapshot["experiences"]) * 25)
    education_score = 100 if snapshot["education"] else 0
    title = snapshot["personal"].get("professional_title", "").lower()
    target_title = (job_description.title or job_description.parsed_json.get("title", "")).lower()
    title_score = 100 if target_title and (target_title in title or title in target_title) else 0
    other_score = 100 if snapshot["summary"] and snapshot["languages"] else 50 if snapshot["summary"] else 0
    overall = round(
        skills_score * 0.35
        + experience_score * 0.25
        + keyword_score * 0.15
        + education_score * 0.10
        + title_score * 0.10
        + other_score * 0.05,
        2,
    )
    missing = sorted(job_words - resume_words)[:50]
    match = JobMatch.objects.create(
        user=resume.user,
        anonymous_identity=resume.anonymous_identity,
        resume=resume,
        job_description=job_description,
        overall_score=overall,
        skills_score=skills_score,
        experience_score=experience_score,
        keyword_score=keyword_score,
        education_score=education_score,
        title_score=title_score,
        other_score=other_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing,
        result_json={
            "formula_version": "1.0",
            "matched_skills": matched_skills,
            "missing_skills": sorted(job_skills - resume_skills),
        },
        report_language=report_language,
    )
    checks = {
        "has_contact_details": bool(snapshot["personal"].get("email") and snapshot["personal"].get("phone")),
        "has_summary": bool(snapshot["summary"]),
        "has_experience": bool(snapshot["experiences"]),
        "has_education": bool(snapshot["education"]),
        "has_three_skills": len(snapshot["skills"]) >= 3,
    }
    ATSReport.objects.create(
        user=resume.user,
        anonymous_identity=resume.anonymous_identity,
        resume=resume,
        job_match=match,
        score=round((sum(checks.values()) / len(checks)) * 100, 2),
        checks=checks,
        recommendations=[REPORT_TEXT[report_language][key] for key, value in checks.items() if not value],
    )
    TemporaryGeneratedResume.objects.create(
        user=resume.user,
        anonymous_identity=resume.anonymous_identity,
        source_resume=resume,
        generated_json=snapshot,
        match_results={
            "job_match_id": match.id,
            "overall_score": overall,
            "matched_keywords": matched_keywords,
            "missing_keywords": missing,
        },
        expires_at=timezone.now() + timedelta(hours=settings.CAREER_SUITE_TEMP_TTL_HOURS),
    )
    return match


@transaction.atomic
def optimize_match(match, target_score=90, confirmed_skills=None, declined_skills=None, output_language="en"):
    language = output_language if output_language in {"en", "nl"} else "en"
    snapshot = resume_snapshot(match.resume)
    snapshot["locale"] = language
    existing_skills = {item["name"].strip().lower() for item in snapshot["skills"]}
    job_skills = {
        skill.strip().lower()
        for skill in (
            match.job_description.parsed_json.get("required_skills")
            or match.job_description.parsed_json.get("skills", [])
        )
    }
    declined = {skill.strip().lower() for skill in (declined_skills or [])}
    confirmed = []
    evidence_lines = []
    for item in confirmed_skills or []:
        normalized = item["skill"].strip().lower()
        if (
            item.get("confirmed")
            and normalized in job_skills
            and normalized not in declined
            and normalized not in existing_skills
        ):
            confirmed.append(item)
            snapshot["skills"].append(
                {
                    "name": item["skill"].strip(),
                    "category": "Confirmed",
                    "level": "",
                    "position": len(snapshot["skills"]),
                }
            )
            if item.get("evidence", "").strip():
                evidence_lines.append(f"{item['skill'].strip()}: {item['evidence'].strip()}")
    matched_names = job_skills & ({item["name"].strip().lower() for item in snapshot["skills"]})
    snapshot["skills"].sort(key=lambda item: item["name"].strip().lower() not in matched_names)
    changes = [
        (
            "Vaardigheden opnieuw geordend op relevantie voor de vacature"
            if language == "nl"
            else "Reordered skills to prioritize job-relevant experience"
        )
    ]
    if confirmed:
        changes.append("Bevestigde vaardigheden toegevoegd" if language == "nl" else "Added confirmed skills")
    if evidence_lines:
        evidence_text = (
            "Bevestigde relevante ervaring: " if language == "nl" else "Confirmed relevant experience: "
        ) + "; ".join(evidence_lines)
        snapshot["summary"] = f"{snapshot.get('summary', '').strip()} {evidence_text}".strip()
        snapshot["confirmed_skill_evidence"] = evidence_lines
        changes.append(
            "Bevestigd bewijs aan het profiel toegevoegd"
            if language == "nl"
            else "Added user-confirmed skill evidence to the professional summary"
        )
    matched_existing = [item["name"] for item in snapshot["skills"] if item["name"].strip().lower() in matched_names][
        :8
    ]
    if matched_existing and snapshot.get("summary"):
        strengths = (
            f"Relevante sterke punten: {', '.join(matched_existing)}."
            if language == "nl"
            else f"Relevant strengths: {', '.join(matched_existing)}."
        )
        if strengths.lower() not in snapshot["summary"].lower():
            snapshot["summary"] = f"{snapshot['summary'].strip()} {strengths}"
            changes.append(
                "Relevante vaardigheden in het profiel benadrukt"
                if language == "nl"
                else "Highlighted existing job-relevant skills in the summary"
            )
    optimized_resume, optimized_version = create_resume_from_snapshot(
        match.user,
        match.resume,
        snapshot,
        title_suffix=f"{'Geoptimaliseerd' if language == 'nl' else 'Optimized'} {target_score}%",
    )
    new_match = analyze_match(optimized_resume, match.job_description, match.user)
    new_score = float(new_match.overall_score)
    remaining_missing_skills = sorted(job_skills - {item["name"].strip().lower() for item in snapshot["skills"]})
    remaining_gaps = []
    for skill in sorted(declined & job_skills):
        remaining_gaps.append(
            f"{skill} is niet toegevoegd omdat de gebruiker dit heeft geweigerd"
            if language == "nl"
            else f"{skill} was not added because the user declined it"
        )
    remaining_gaps.extend(
        (f"{skill} is niet gevonden of bevestigd" if language == "nl" else f"{skill} was not found or confirmed")
        for skill in remaining_missing_skills
        if skill not in declined
    )
    if new_score < target_score:
        remaining_gaps.insert(
            0,
            (
                f"Het doel was {target_score}%, maar de eerlijke geoptimaliseerde match is {new_score:.0f}% "
                "omdat vereiste feiten niet zijn gevonden of bevestigd."
                if language == "nl"
                else f"Target was {target_score}%, but the honest optimized match is {new_score:.0f}% because required facts were not found or confirmed."
            ),
        )
    optimized = OptimizedResume.objects.create(
        user=match.user,
        anonymous_identity=match.anonymous_identity,
        source_resume=match.resume,
        optimized_resume=optimized_resume,
        job_match=match,
        optimized_json=snapshot,
        suggestions=changes,
        confirmation_required_skills=remaining_missing_skills,
        output_language=language,
    )
    TemporaryGeneratedResume.objects.create(
        user=match.user,
        anonymous_identity=match.anonymous_identity,
        source_resume=match.resume,
        generated_json=optimized.optimized_json,
        match_results={
            "job_match_id": match.id,
            "original_score": float(match.overall_score),
            "new_score": new_score,
            "target_score": target_score,
            "output_language": language,
        },
        expires_at=timezone.now() + timedelta(hours=settings.CAREER_SUITE_TEMP_TTL_HOURS),
    )
    return {
        "optimized": optimized,
        "optimized_resume": optimized_resume,
        "optimized_version": optimized_version,
        "new_match": new_match,
        "changes": changes,
        "remaining_gaps": remaining_gaps,
    }
