from django.utils import timezone

from apps.exports.services import save_export
from apps.files.models import UserFile
from apps.resumes.models import Resume, ResumeUpload, TemporaryGeneratedResume, TemporaryResumeUpload
from apps.resumes.services import parse_upload

from .models import JobMatch, TemporaryJobDescription
from .services import analyze_match, optimize_match, parse_job_url


def parse_resume_file_job(upload_id):
    return parse_upload(ResumeUpload.objects.get(id=upload_id))


def parse_job_url_job(url):
    return parse_job_url(url)


def analyze_job_match_job(resume, job_description, user):
    return analyze_match(resume, job_description, user)


def generate_pdf_job(resume_id):
    return save_export(Resume.objects.get(id=resume_id), "pdf")


def generate_docx_job(resume_id):
    return save_export(Resume.objects.get(id=resume_id), "docx")


def optimize_resume_job(match_id):
    return optimize_match(JobMatch.objects.get(id=match_id))


def delete_expired_temp_data_job():
    now = timezone.now()
    counts = {}
    for model in (TemporaryResumeUpload, TemporaryGeneratedResume, TemporaryJobDescription):
        deleted, _ = model.objects.filter(expires_at__lte=now).delete()
        counts[model.__name__] = deleted
    expired_files, _ = UserFile.objects.filter(expires_at__isnull=False, expires_at__lte=now).delete()
    counts["UserFile"] = expired_files
    return counts
