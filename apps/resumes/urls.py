from django.urls import include, path

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("resumes", views.ResumeViewSet, basename="resume")

urlpatterns = [
    path("resume-builder/auto-fill-from-job/", views.auto_fill_from_job),
    path("resume-builder/auto-fill-drafts/<int:draft_id>/", views.auto_fill_draft),
    path("resumes/my-anonymous/", views.my_anonymous_resume),
    path("resumes/claim-anonymous/", views.claim_anonymous_resume),
    path("resumes/upload/", views.upload_resume),
    path("resumes/parse/", views.parse_resume),
    path("resumes/<int:resume_id>/personal/", views.update_personal),
    path("resumes/<int:resume_id>/summary/", views.update_summary),
    path("resumes/<int:resume_id>/generate-summary/", views.generate_summary),
    path("resumes/<int:resume_id>/generate-skills/", views.generate_skills),
    path("resumes/<int:resume_id>/experiences/", views.create_experience),
    path("experiences/<int:item_id>/", views.section_detail, {"section": "experiences"}),
    path("resumes/<int:resume_id>/education/", views.create_education),
    path("resumes/<int:resume_id>/projects/", views.create_project),
    path("resumes/<int:resume_id>/skills/", views.create_skill),
    path("resumes/<int:resume_id>/certifications/", views.create_certification),
    path("resumes/<int:resume_id>/languages/", views.create_language),
    path("resumes/<int:resume_id>/awards/", views.create_award),
    path("resumes/<int:resume_id>/references/", views.create_reference),
    path("resumes/<int:resume_id>/photo/upload/", views.resume_photo),
    path("resumes/<int:resume_id>/photo/", views.resume_photo_detail),
    path("resumes/<int:resume_id>/select-template/", views.select_template),
    path("resumes/<int:resume_id>/preview/", views.preview_resume),
    path("education/<int:item_id>/", views.section_detail, {"section": "education"}),
    path("projects/<int:item_id>/", views.section_detail, {"section": "projects"}),
    path("skills/<int:item_id>/", views.section_detail, {"section": "skills"}),
    path("certifications/<int:item_id>/", views.section_detail, {"section": "certifications"}),
    path("languages/<int:item_id>/", views.section_detail, {"section": "languages"}),
    path("awards/<int:item_id>/", views.section_detail, {"section": "awards"}),
    path("references/<int:item_id>/", views.section_detail, {"section": "references"}),
    path("resumes/<int:resume_id>/export/<str:output_format>/", views.export_resume),
    path("", include(router.urls)),
]
