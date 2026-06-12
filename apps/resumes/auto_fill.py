import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import JobDescription
from apps.jobs.services import canonical_skill, parse_job_text, parse_job_url

from .limits import can_create_resume, can_edit_resume, get_owned_resume
from .models import (
    PersonalDetail,
    Resume,
    ResumeSummary,
    ResumeUpload,
    Skill,
    TemporaryGeneratedResume,
)
from .services import create_resume_from_snapshot, create_version, parse_upload, resume_snapshot


TEXT = {
    "en": {
        "summary_placeholder": "Add a factual professional summary tailored to this role.",
        "experience_placeholder": "Add your real experience with {responsibility} here.",
        "experience_generic": "Add your real work experience relevant to this role here.",
        "education_placeholder": "Add your real education and training here.",
        "skill_question": "Do you have real experience with {value}?",
        "certification_question": "Do you hold the {value} certification?",
        "education_question": "Do you meet this education requirement: {value}?",
        "title_question": "Should your target professional title be {value}?",
        "suggestion_warning": (
            "Some skills and certifications were suggested from the job description and need your confirmation."
        ),
        "no_resume_warning": (
            "We created a starter resume draft from the job description. "
            "Please add your real experience before exporting."
        ),
        "upload_structure_warning": (
            "The uploaded CV did not contain enough structured experience or education data; "
            "review those sections before exporting."
        ),
        "targeting": "Targeting {title} roles.",
        "strengths": "Relevant strengths supported by the source resume: {skills}.",
    },
    "nl": {
        "summary_placeholder": "Voeg een feitelijk professioneel profiel toe dat past bij deze functie.",
        "experience_placeholder": "Voeg hier je echte ervaring met {responsibility} toe.",
        "experience_generic": "Voeg hier je echte werkervaring toe die relevant is voor deze functie.",
        "education_placeholder": "Voeg hier je echte opleiding en training toe.",
        "skill_question": "Heb je echte ervaring met {value}?",
        "certification_question": "Heb je het certificaat {value}?",
        "education_question": "Voldoe je aan deze opleidingseis: {value}?",
        "title_question": "Wil je {value} als beoogde functietitel gebruiken?",
        "suggestion_warning": (
            "Sommige vaardigheden en certificaten zijn voorgesteld op basis van de vacature "
            "en moeten worden bevestigd."
        ),
        "no_resume_warning": (
            "We hebben een eerste cv-concept gemaakt op basis van de vacature. "
            "Voeg je echte ervaring toe voordat je exporteert."
        ),
        "upload_structure_warning": (
            "Het geüploade cv bevatte onvoldoende gestructureerde werkervaring of opleidingsgegevens; "
            "controleer deze onderdelen voordat je exporteert."
        ),
        "targeting": "Gericht op functies als {title}.",
        "strengths": "Relevante sterke punten uit het bron-cv: {skills}.",
    },
}


class AutoFillResumeService:
    def __init__(self, request):
        self.request = request

    def execute(self, validated_data):
        language = validated_data["target_language"]
        parsed_job, job_text, source_url, existing_job = self._parse_job(validated_data)
        source_resume = self._source_resume(validated_data.get("resume_id"))
        upload = self._source_upload(validated_data.get("uploaded_resume_id"))
        parsed_resume = self._parsed_upload(upload) if upload else None
        if source_resume and source_resume.anonymous_identity_id:
            can_edit_resume(source_resume, self.request)
            identity = source_resume.anonymous_identity
        else:
            identity = can_create_resume(
                self.request,
                email=validated_data.get("owner_email"),
                phone=validated_data.get("owner_phone"),
            )

        with transaction.atomic():
            job = existing_job or self._save_job(parsed_job, job_text, source_url, language, identity)
            resume = self._create_resume(source_resume, parsed_resume, parsed_job, language, identity)
            if source_resume and source_resume.anonymous_identity_id:
                source_resume.is_archived = True
                source_resume.save(update_fields=["is_archived", "updated_at"])
            payload = self._build_payload(resume, source_resume, parsed_resume, parsed_job, language)
            draft = TemporaryGeneratedResume.objects.create(
                user=resume.user,
                anonymous_identity=resume.anonymous_identity,
                source_resume=source_resume or resume,
                generated_json=payload,
                match_results={
                    "job_description_id": job.id,
                    "resume_id": resume.id,
                    "target_match_score": validated_data["target_match_score"],
                    "confidence_score": payload["confidence_score"],
                    "requires_user_review": True,
                    "generation_type": "auto_fill_from_job",
                },
                expires_at=timezone.now() + timedelta(hours=settings.CAREER_SUITE_TEMP_TTL_HOURS),
            )

        return {
            "success": True,
            "resume_id": str(resume.id),
            "draft_id": str(draft.id),
            "job_description_id": str(job.id),
            "auto_filled": True,
            "confidence_score": payload["confidence_score"],
            "requires_user_review": True,
            "builder_payload": payload["builder_payload"],
            "warnings": payload["warnings"],
        }

    def _parse_job(self, data):
        job_id = data.get("job_description_id")
        if job_id:
            if self.request.user.is_authenticated:
                job = JobDescription.objects.get(id=job_id, user=self.request.user)
            else:
                from .anonymous_identity import resolve_anonymous_identity

                identity = resolve_anonymous_identity(self.request, create=False)
                if not identity:
                    raise JobDescription.DoesNotExist
                job = JobDescription.objects.get(id=job_id, anonymous_identity=identity)
            return job.parsed_json or parse_job_text(job.raw_text), job.raw_text, job.source_url, job
        text = data.get("job_description_text", "").strip()
        url = data.get("job_description_url", "").strip()
        if text:
            return parse_job_text(text), text, url, None
        parsed = parse_job_url(url)
        return parsed, parsed["raw_text"], url, None

    def _source_resume(self, resume_id):
        return get_owned_resume(self.request, id=resume_id) if resume_id else None

    def _source_upload(self, upload_id):
        if not upload_id:
            return None
        if self.request.user.is_authenticated:
            return ResumeUpload.objects.get(id=upload_id, user=self.request.user)
        from .anonymous_identity import resolve_anonymous_identity

        identity = resolve_anonymous_identity(self.request, create=False)
        if not identity:
            raise ResumeUpload.DoesNotExist
        return ResumeUpload.objects.get(id=upload_id, anonymous_identity=identity)

    @staticmethod
    def _parsed_upload(upload):
        return upload.parsed_json if upload.status == "completed" else parse_upload(upload)

    def _save_job(self, parsed, raw_text, source_url, language, identity):
        return JobDescription.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            anonymous_identity=identity,
            title=parsed.get("job_title") or parsed.get("title", ""),
            company=parsed.get("company", ""),
            source_url=source_url,
            raw_text=raw_text,
            parsed_json=parsed,
            language=language,
        )

    def _create_resume(self, source_resume, parsed_resume, parsed_job, language, identity):
        target_title = parsed_job.get("job_title") or parsed_job.get("title", "")
        if source_resume:
            snapshot = resume_snapshot(source_resume)
            snapshot["locale"] = language
            snapshot["summary"] = self._tailored_summary(
                snapshot.get("summary", ""),
                target_title,
                self._matched_skill_names(snapshot.get("skills", []), parsed_job),
                language,
            )
            if target_title:
                personal = snapshot.setdefault("personal", {})
                existing_title = personal.get("professional_title", "")
                if not existing_title or self._titles_close(existing_title, target_title):
                    personal["professional_title"] = target_title
            for experience in snapshot.get("experiences", []):
                experience["description"] = self._prioritize_existing_text(
                    experience.get("description", ""),
                    parsed_job.get("keywords", []),
                )
            resume, _ = create_resume_from_snapshot(
                self.request.user if self.request.user.is_authenticated else None,
                source_resume,
                snapshot,
                title_suffix="Vacatureconcept" if language == "nl" else "Job Draft",
                version_source="auto_fill_from_job",
            )
            return resume

        resume = Resume.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            anonymous_identity=identity,
            title=(
                f"{target_title} - Vacatureconcept"
                if language == "nl" and target_title
                else (
                    f"{target_title} - Job Draft"
                    if target_title
                    else "Vacatureconcept" if language == "nl" else "Job Draft"
                )
            ),
            locale=language,
            source="registered" if self.request.user.is_authenticated else "anonymous",
        )
        personal = self._personal_from_upload_or_profile(parsed_resume)
        if target_title:
            personal["professional_title"] = target_title
        PersonalDetail.objects.create(resume=resume, **personal)
        existing_summary = (parsed_resume or {}).get("summary", "")
        matched_skills = self._matched_skill_names((parsed_resume or {}).get("skills", []), parsed_job)
        ResumeSummary.objects.create(
            resume=resume,
            text=self._tailored_summary(existing_summary, target_title, matched_skills, language),
        )
        for position, skill in enumerate((parsed_resume or {}).get("skills", [])):
            name = skill.get("name", "").strip()
            if name:
                Skill.objects.get_or_create(
                    resume=resume,
                    name=name,
                    defaults={"category": skill.get("category", ""), "position": position},
                )
        create_version(resume, source="auto_fill_from_job")
        return resume

    def _personal_from_upload_or_profile(self, parsed_resume):
        personal = dict((parsed_resume or {}).get("personal", {}))
        allowed = {
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "country",
            "professional_title",
            "address",
            "postal_code",
            "linkedin_url",
            "portfolio_url",
        }
        personal = {key: value for key, value in personal.items() if key in allowed and value}
        if self.request.user.is_authenticated:
            personal.setdefault("first_name", self.request.user.first_name)
            personal.setdefault("last_name", self.request.user.last_name)
            personal.setdefault("email", self.request.user.email)
        return personal

    def _build_payload(self, resume, source_resume, parsed_resume, parsed_job, language):
        labels = TEXT[language]
        snapshot = resume_snapshot(resume)
        job_skills = self._job_skills(parsed_job)
        confirmed_by_name = {
            canonical_skill(item["name"]): item for item in snapshot["skills"] if item.get("name", "").strip()
        }
        skills = [
            {
                "name": item["name"],
                "category": item.get("category", ""),
                "source": "existing_resume" if source_resume else "uploaded_resume",
                "status": "confirmed",
            }
            for item in snapshot["skills"]
        ]
        suggested_skills = []
        review_questions = []
        for name in job_skills:
            if canonical_skill(name) in confirmed_by_name:
                continue
            suggestion = {
                "name": name,
                "category": self._skill_category(name, parsed_job),
                "source": "job_description",
                "status": "needs_confirmation",
            }
            suggested_skills.append(suggestion)
            review_questions.append(
                {
                    "type": "skill_confirmation",
                    "question": labels["skill_question"].format(value=name),
                    "field": name,
                }
            )
        skills.extend(suggested_skills)

        certifications = [
            {
                "name": item["name"],
                "issuer": item.get("issuer", ""),
                "source": "existing_resume",
                "status": "confirmed",
            }
            for item in snapshot["certifications"]
        ]
        confirmed_certifications = {item["name"].strip().casefold() for item in certifications}
        for requirement in parsed_job.get("certifications", []):
            name = requirement.strip()
            if not name or name.casefold() in confirmed_certifications:
                continue
            certifications.append({"name": name, "source": "job_description", "status": "needs_confirmation"})
            review_questions.append(
                {
                    "type": "certification_confirmation",
                    "question": labels["certification_question"].format(value=name),
                    "field": name,
                }
            )

        education_requirements = parsed_job.get("education_requirements") or parsed_job.get("education", [])
        if not snapshot["education"]:
            for requirement in education_requirements:
                review_questions.append(
                    {
                        "type": "education_gap",
                        "question": labels["education_question"].format(value=requirement),
                        "field": requirement,
                    }
                )

        original_title = ""
        if source_resume and hasattr(source_resume, "personal"):
            original_title = source_resume.personal.professional_title
        target_title = parsed_job.get("job_title") or parsed_job.get("title", "")
        if target_title and original_title and not self._titles_close(original_title, target_title):
            review_questions.append(
                {
                    "type": "professional_title_review",
                    "question": labels["title_question"].format(value=target_title),
                    "field": target_title,
                }
            )

        experiences = [
            {
                "job_title": item.get("job_title", ""),
                "company": item.get("employer", ""),
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
                "current": item.get("current", False),
                "bullets": self._description_bullets(item.get("description", "")),
                "source": "existing_resume",
                "status": "confirmed",
            }
            for item in snapshot["experiences"]
        ]
        if not experiences:
            responsibilities = parsed_job.get("responsibilities", [])[:3]
            experiences = [
                {
                    "job_title": "",
                    "company": "",
                    "bullets": [
                        labels["experience_placeholder"].format(responsibility=value) for value in responsibilities
                    ]
                    or [labels["experience_generic"]],
                    "source": "job_description",
                    "status": "needs_user_input",
                }
            ]

        education = [{**item, "source": "existing_resume", "status": "confirmed"} for item in snapshot["education"]]
        if not education:
            education = [
                {
                    "institution": "",
                    "degree": "",
                    "field_of_study": "",
                    "description": labels["education_placeholder"],
                    "source": "job_description",
                    "status": "needs_user_input",
                }
            ]

        warnings = []
        if suggested_skills or any(item["status"] == "needs_confirmation" for item in certifications):
            warnings.append(labels["suggestion_warning"])
        if not source_resume and not parsed_resume:
            warnings.append(labels["no_resume_warning"])
        elif parsed_resume and not source_resume and not (snapshot["experiences"] or snapshot["education"]):
            warnings.append(labels["upload_structure_warning"])

        confirmed_sections = sum(
            bool(value)
            for value in (
                snapshot["personal"].get("email"),
                snapshot["summary"],
                snapshot["skills"],
                snapshot["experiences"],
                snapshot["education"],
            )
        )
        confidence = min(95, 35 + confirmed_sections * 10 + min(len(confirmed_by_name), 5) * 2)
        summary_text = snapshot["summary"] or labels["summary_placeholder"]
        source_summary = (
            source_resume.summary.text
            if source_resume and hasattr(source_resume, "summary")
            else (parsed_resume or {}).get("summary", "")
        )
        summary_status = "confirmed" if source_summary else "needs_user_input"
        return {
            "confidence_score": confidence,
            "warnings": warnings,
            "builder_payload": {
                "personal_details": snapshot["personal"],
                "summary": {
                    "text": summary_text,
                    "source": (
                        "existing_resume" if source_resume else "uploaded_resume" if parsed_resume else "placeholder"
                    ),
                    "status": summary_status,
                },
                "skills": skills,
                "experience": experiences,
                "education": education,
                "projects": [
                    {**item, "source": "existing_resume", "status": "confirmed"} for item in snapshot["projects"]
                ],
                "certifications": certifications,
                "languages": [
                    {**item, "source": "existing_resume", "status": "confirmed"} for item in snapshot["languages"]
                ],
                "review_questions": review_questions,
                "job_description": {
                    "job_title": target_title,
                    "company": parsed_job.get("company", ""),
                    "location": parsed_job.get("location", ""),
                    "seniority": parsed_job.get("seniority", ""),
                    "required_skills": parsed_job.get("required_skills", []),
                    "preferred_skills": parsed_job.get("preferred_skills", []),
                    "responsibilities": parsed_job.get("responsibilities", []),
                    "tools": parsed_job.get("tools", []),
                    "technologies": parsed_job.get("technologies", []),
                    "education_requirements": education_requirements,
                    "certifications": parsed_job.get("certifications", []),
                    "keywords": parsed_job.get("keywords", []),
                    "language_requirements": parsed_job.get("language_requirements", []),
                },
            },
        }

    @staticmethod
    def _job_skills(parsed_job):
        values = (
            parsed_job.get("required_skills", [])
            + parsed_job.get("preferred_skills", [])
            + parsed_job.get("tools", [])
            + parsed_job.get("technologies", [])
        )
        unique = []
        seen = set()
        for value in values:
            normalized = canonical_skill(value)
            if normalized not in seen:
                seen.add(normalized)
                unique.append(value)
        return unique

    @classmethod
    def _matched_skill_names(cls, skills, parsed_job):
        job_skills = {canonical_skill(value) for value in cls._job_skills(parsed_job)}
        return [item["name"] for item in skills if canonical_skill(item.get("name", "")) in job_skills]

    @staticmethod
    def _tailored_summary(existing_summary, target_title, matched_skills, language):
        labels = TEXT[language]
        parts = [existing_summary.strip()]
        if target_title:
            parts.append(labels["targeting"].format(title=target_title))
        if matched_skills:
            parts.append(labels["strengths"].format(skills=", ".join(matched_skills[:8])))
        return " ".join(part for part in parts if part)

    @staticmethod
    def _prioritize_existing_text(text, keywords):
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", text) if item.strip()]
        keyword_set = {word.casefold() for word in keywords[:50]}
        sentences.sort(
            key=lambda sentence: -sum(
                1 for word in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9+#.-]*", sentence.casefold()) if word in keyword_set
            )
        )
        return " ".join(sentences)

    @staticmethod
    def _description_bullets(description):
        return [item.strip(" -•") for item in re.split(r"(?<=[.!?])\s+|\n+", description) if item.strip(" -•")]

    @staticmethod
    def _skill_category(name, parsed_job):
        canonical = canonical_skill(name)
        tools = {canonical_skill(value) for value in parsed_job.get("tools", [])}
        technologies = {canonical_skill(value) for value in parsed_job.get("technologies", [])}
        return "Technical" if canonical in tools | technologies else "Suggested"

    @staticmethod
    def _titles_close(existing, target):
        existing_words = set(re.findall(r"\w+", existing.casefold()))
        target_words = set(re.findall(r"\w+", target.casefold()))
        return bool(existing_words & target_words)
