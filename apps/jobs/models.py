from django.conf import settings
from django.db import models


class JobDescription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="job_descriptions"
    )
    anonymous_identity = models.ForeignKey(
        "resumes.AnonymousResumeIdentity", null=True, blank=True, on_delete=models.CASCADE
    )
    title = models.CharField(max_length=255, blank=True)
    company = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(blank=True)
    raw_text = models.TextField()
    parsed_json = models.JSONField(default=dict, blank=True)
    language = models.CharField(max_length=10, choices=[("en", "English"), ("nl", "Dutch")], default="en")
    created_at = models.DateTimeField(auto_now_add=True)


class TemporaryJobDescription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    anonymous_identity = models.ForeignKey(
        "resumes.AnonymousResumeIdentity", null=True, blank=True, on_delete=models.CASCADE
    )
    raw_text = models.TextField()
    parsed_json = models.JSONField(default=dict, blank=True)
    source_url = models.URLField(blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class JobMatch(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    anonymous_identity = models.ForeignKey(
        "resumes.AnonymousResumeIdentity", null=True, blank=True, on_delete=models.CASCADE
    )
    resume = models.ForeignKey("resumes.Resume", on_delete=models.CASCADE, related_name="job_matches")
    job_description = models.ForeignKey(JobDescription, on_delete=models.CASCADE, related_name="matches")
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    skills_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    experience_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    keyword_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    education_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    title_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    other_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    matched_keywords = models.JSONField(default=list, blank=True)
    missing_keywords = models.JSONField(default=list, blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="completed")
    report_language = models.CharField(max_length=10, choices=[("en", "English"), ("nl", "Dutch")], default="en")
    created_at = models.DateTimeField(auto_now_add=True)


class ATSReport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    anonymous_identity = models.ForeignKey(
        "resumes.AnonymousResumeIdentity", null=True, blank=True, on_delete=models.CASCADE
    )
    resume = models.ForeignKey("resumes.Resume", on_delete=models.CASCADE, related_name="ats_reports")
    job_match = models.OneToOneField(
        JobMatch, null=True, blank=True, on_delete=models.CASCADE, related_name="ats_report"
    )
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    checks = models.JSONField(default=dict)
    recommendations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
