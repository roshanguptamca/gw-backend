import io
import json
import re
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from docx import Document as DocxDocument
from pypdf import PdfReader

from apps.resumes.models import (
    Award,
    Certification,
    Education,
    PersonalDetail,
    Project,
    Reference,
    ResumeLanguage,
    ResumeSummary,
    Skill,
    TemporaryResumeUpload,
    WorkExperience,
)

SECTION_MODELS = {
    "experiences": WorkExperience,
    "education": Education,
    "projects": Project,
    "skills": Skill,
    "certifications": Certification,
    "languages": ResumeLanguage,
    "awards": Award,
    "references": Reference,
}

STOP_WORDS = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "that",
    "this",
    "your",
    "you",
    "our",
    "are",
    "will",
    "have",
    "has",
    "job",
    "role",
    "work",
    "years",
    "about",
    "into",
    "their",
    "they",
    "but",
    "not",
    "all",
    "who",
    "aan",
    "als",
    "ben",
    "bij",
    "binnen",
    "dat",
    "de",
    "deze",
    "die",
    "dit",
    "een",
    "en",
    "er",
    "ervaring",
    "het",
    "in",
    "is",
    "je",
    "jij",
    "jou",
    "met",
    "naar",
    "niet",
    "of",
    "om",
    "onze",
    "op",
    "te",
    "van",
    "voor",
    "we",
    "werken",
    "worden",
    "jaar",
    "zijn",
}


def resume_snapshot(resume):
    data = {
        "id": resume.id,
        "title": resume.title,
        "locale": resume.locale,
        "template": resume.template_id,
        "template_settings": resume.template_settings,
        "include_photo": resume.include_photo,
        "personal": model_to_dict(resume.personal) if hasattr(resume, "personal") else {},
        "summary": resume.summary.text if hasattr(resume, "summary") else "",
    }
    data["personal"].pop("id", None)
    data["personal"].pop("resume", None)
    data["personal"].pop("profile_photo", None)
    photo_id = resume.personal.profile_photo_id if hasattr(resume, "personal") else None
    data["personal"]["profile_photo_id"] = str(photo_id) if photo_id else None
    data["personal"]["template_supports_photo"] = bool(resume.template and resume.template.supports_photo)
    for name, model in SECTION_MODELS.items():
        data[name] = []
        for item in model.objects.filter(resume=resume):
            item_data = model_to_dict(item)
            item_data.pop("resume", None)
            data[name].append(item_data)
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def create_version(resume, source="manual", snapshot=None):
    number = (resume.versions.order_by("-version_number").values_list("version_number", flat=True).first() or 0) + 1
    snapshot_data = snapshot if snapshot is not None else resume_snapshot(resume)
    return resume.versions.create(
        version_number=number,
        snapshot=json.loads(json.dumps(snapshot_data, cls=DjangoJSONEncoder)),
        source=source,
    )


def extract_resume_text(upload):
    content = bytes(upload.file_data)
    extension = upload.filename.rsplit(".", 1)[-1].lower()
    if extension == "pdf":
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if extension == "docx":
        document = DocxDocument(io.BytesIO(content))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(paragraphs).strip()
    if extension == "txt":
        return content.decode("utf-8", errors="replace").strip()
    raise ValueError("Supported resume formats are PDF, DOCX, and TXT.")


def parse_resume_text(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
    name_parts = lines[0].split() if lines else []
    headings = {
        "experience": ["experience", "employment", "work history"],
        "education": ["education", "academic"],
        "skills": ["skills", "technologies", "competencies"],
        "summary": ["summary", "profile", "objective"],
    }
    sections = {key: [] for key in headings}
    current = None
    for line in lines[1:]:
        normalized = line.lower().rstrip(":")
        matched = next((key for key, values in headings.items() if normalized in values), None)
        if matched:
            current = matched
        elif current:
            sections[current].append(line)
    skills = []
    for line in sections["skills"]:
        skills.extend(part.strip() for part in re.split(r"[,|•]", line) if part.strip())
    return {
        "personal": {
            "first_name": name_parts[0] if name_parts else "",
            "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
            "email": email_match.group(0) if email_match else "",
            "phone": phone_match.group(0).strip() if phone_match else "",
        },
        "summary": " ".join(sections["summary"]),
        "experience_text": "\n".join(sections["experience"]),
        "education_text": "\n".join(sections["education"]),
        "skills": [{"name": skill} for skill in skills[:50]],
        "raw_text": text,
    }


def parse_upload(upload):
    upload.status = "processing"
    upload.save(update_fields=["status", "updated_at"])
    try:
        text = extract_resume_text(upload)
        parsed = parse_resume_text(text)
        upload.extracted_text = text
        upload.parsed_json = parsed
        upload.status = "completed"
        upload.error_message = ""
        upload.save()
        TemporaryResumeUpload.objects.create(
            user=upload.user,
            anonymous_identity=upload.anonymous_identity,
            upload=upload,
            extracted_text=text,
            parsed_json=parsed,
            expires_at=timezone.now() + timedelta(hours=settings.CAREER_SUITE_TEMP_TTL_HOURS),
        )
        return parsed
    except Exception as exc:
        upload.status = "failed"
        upload.error_message = str(exc)
        upload.save(update_fields=["status", "error_message", "updated_at"])
        raise


def keyword_counts(text):
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}", text.lower())
    return Counter(word for word in words if word not in STOP_WORDS)


def apply_parsed_resume(resume, parsed):
    personal_data = parsed.get("personal", {})
    allowed = {field.name for field in PersonalDetail._meta.fields} - {"id", "resume"}
    PersonalDetail.objects.update_or_create(
        resume=resume, defaults={key: value for key, value in personal_data.items() if key in allowed}
    )
    ResumeSummary.objects.update_or_create(resume=resume, defaults={"text": parsed.get("summary", "")})
    for skill in parsed.get("skills", []):
        if skill.get("name"):
            Skill.objects.get_or_create(resume=resume, name=skill["name"], defaults={"position": 0})
    create_version(resume, source="upload")
    return resume


def _snapshot_item_key(section, item):
    normalize = lambda value: re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    if section == "skills":
        return (normalize(item.get("name")),)
    if section == "education":
        return (
            normalize(item.get("institution")),
            normalize(item.get("degree")),
            normalize(item.get("field_of_study")),
            str(item.get("start_date") or ""),
        )
    if section == "experiences":
        return (
            normalize(item.get("employer")),
            normalize(item.get("job_title")),
            str(item.get("start_date") or ""),
        )
    if section == "projects":
        return (normalize(item.get("name")), normalize(item.get("role")))
    return None


@transaction.atomic
def create_resume_from_snapshot(
    user,
    source_resume,
    snapshot,
    title_suffix="Optimized",
    version_source="ai_optimization",
):
    resume = source_resume.__class__.objects.create(
        user=source_resume.user,
        anonymous_identity=source_resume.anonymous_identity,
        title=f"{source_resume.title} - {title_suffix}",
        locale=snapshot.get("locale", source_resume.locale),
        template=source_resume.template,
        template_settings=source_resume.template_settings,
        include_photo=source_resume.include_photo,
        source=source_resume.source,
        max_edit_count=source_resume.max_edit_count,
    )
    personal_data = snapshot.get("personal", {}).copy()
    personal_data.pop("profile_photo_id", None)
    personal_data.pop("template_supports_photo", None)
    personal_data.pop("photo_url", None)
    allowed = {field.name for field in PersonalDetail._meta.fields} - {"id", "resume", "profile_photo"}
    personal = PersonalDetail.objects.create(
        resume=resume,
        profile_photo=source_resume.personal.profile_photo if hasattr(source_resume, "personal") else None,
        **{key: value for key, value in personal_data.items() if key in allowed},
    )
    if hasattr(source_resume, "personal"):
        personal.include_photo = source_resume.personal.include_photo
        personal.save(update_fields=["include_photo"])
    ResumeSummary.objects.create(resume=resume, text=snapshot.get("summary", ""))
    for section, model in SECTION_MODELS.items():
        allowed_fields = {field.name for field in model._meta.fields} - {
            "id",
            "resume",
            "created_at",
            "updated_at",
            "normalized_name",
            "duplicate_key",
        }
        seen = set()
        for item in snapshot.get(section, []):
            item_key = _snapshot_item_key(section, item)
            if item_key is not None and item_key in seen:
                continue
            if item_key is not None:
                seen.add(item_key)
            model.objects.create(
                resume=resume,
                **{key: value for key, value in item.items() if key in allowed_fields},
            )
    version = create_version(resume, source=version_source)
    return resume, version
