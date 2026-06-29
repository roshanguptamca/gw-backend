from django.db.models import Q

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.resumes.models import Education, PersonalDetail, Skill, WorkExperience

CURATED = {
    "skills": [
        ("React", "Technical"),
        ("Next.js", "Technical"),
        ("Django", "Technical"),
        ("Python", "Technical"),
        ("JavaScript", "Technical"),
        ("TypeScript", "Technical"),
        ("PostgreSQL", "Technical"),
        ("REST API", "Technical"),
        ("Docker", "Tool"),
        ("Kubernetes", "Tool"),
        ("AWS", "Tool"),
        ("Azure", "Tool"),
        ("Git", "Tool"),
        ("Agile", "Methodology"),
        ("Scrum", "Methodology"),
        ("Project Management", "Soft Skill"),
        ("Stakeholder Management", "Soft Skill"),
        ("Communication", "Soft Skill"),
        ("Leadership", "Soft Skill"),
    ],
    "job-titles": [
        ("Software Engineer", ""),
        ("Frontend Developer", ""),
        ("Backend Developer", ""),
        ("Full Stack Developer", ""),
        ("Product Manager", ""),
        ("Project Manager", ""),
        ("Data Analyst", ""),
        ("Data Scientist", ""),
        ("DevOps Engineer", ""),
        ("UX Designer", ""),
    ],
    "companies": [("Google", ""), ("Microsoft", ""), ("Amazon", ""), ("Meta", ""), ("Apple", "")],
    "schools": [
        ("University of Amsterdam", ""),
        ("Delft University of Technology", ""),
        ("Erasmus University Rotterdam", ""),
        ("University of Oxford", ""),
        ("University of Cambridge", ""),
    ],
    "degrees": [
        ("Bachelor of Science", ""),
        ("Bachelor of Arts", ""),
        ("Master of Science", ""),
        ("Master of Arts", ""),
        ("Master of Business Administration", ""),
        ("Doctor of Philosophy", ""),
    ],
    "locations": [
        ("Amsterdam, Netherlands", ""),
        ("Rotterdam, Netherlands", ""),
        ("The Hague, Netherlands", ""),
        ("Utrecht, Netherlands", ""),
        ("London, United Kingdom", ""),
        ("Berlin, Germany", ""),
        ("Paris, France", ""),
        ("New York, United States", ""),
    ],
}
SKILL_TRANSLATIONS = {
    "Project Management": "Projectmanagement",
    "Stakeholder Management": "Stakeholdermanagement",
    "Communication": "Communicatie",
    "Leadership": "Leiderschap",
    "Customer Service": "Klantenservice",
    "Sales": "Verkoop",
    "Accounting": "Boekhouding",
    "Data Analysis": "Data-analyse",
    "Software Development": "Softwareontwikkeling",
}
CURATED["skills"].extend(
    [
        (value, "Soft Skill")
        for value in ("Customer Service", "Sales", "Accounting", "Data Analysis", "Software Development")
    ]
)


def _results(request, kind, database_values):
    query = request.query_params.get("q", "").strip()
    if len(query) < 2:
        return Response({"results": []})
    language = request.query_params.get("lang", "en")
    query_key = query.casefold()
    combined = {}
    for value, category in database_values:
        if value and query_key in value.casefold():
            combined[value.casefold()] = {"label": value, "value": value, "category": category or ""}
    for value, category in CURATED[kind]:
        localized = SKILL_TRANSLATIONS.get(value, value) if kind == "skills" and language == "nl" else value
        if query_key in value.casefold() or query_key in localized.casefold():
            combined.setdefault(
                value.casefold(),
                {
                    "label": localized,
                    "value": value,
                    "canonical": value.casefold(),
                    "language": language,
                    "category": category,
                },
            )
    ordered = sorted(
        combined.values(),
        key=lambda item: (not item["label"].casefold().startswith(query_key), item["label"].casefold()),
    )
    return Response({"results": ordered[:20]})


@api_view(["GET"])
@permission_classes([AllowAny])
def skills(request):
    values = (
        Skill.objects.filter(resume__user=request.user).values_list("name", "category").distinct()
        if request.user.is_authenticated
        else []
    )
    return _results(request, "skills", values)


@api_view(["GET"])
@permission_classes([AllowAny])
def job_titles(request):
    values = (
        WorkExperience.objects.filter(resume__user=request.user).values_list("job_title", flat=True).distinct()
        if request.user.is_authenticated
        else []
    )
    personal = (
        PersonalDetail.objects.filter(resume__user=request.user).values_list("professional_title", flat=True).distinct()
        if request.user.is_authenticated
        else []
    )
    return _results(request, "job-titles", [(value, "") for value in [*values, *personal]])


@api_view(["GET"])
@permission_classes([AllowAny])
def companies(request):
    values = (
        WorkExperience.objects.filter(resume__user=request.user).values_list("employer", flat=True).distinct()
        if request.user.is_authenticated
        else []
    )
    return _results(request, "companies", [(value, "") for value in values])


@api_view(["GET"])
@permission_classes([AllowAny])
def schools(request):
    values = (
        Education.objects.filter(resume__user=request.user).values_list("institution", flat=True).distinct()
        if request.user.is_authenticated
        else []
    )
    return _results(request, "schools", [(value, "") for value in values])


@api_view(["GET"])
@permission_classes([AllowAny])
def degrees(request):
    values = (
        Education.objects.filter(resume__user=request.user).values_list("degree", flat=True).distinct()
        if request.user.is_authenticated
        else []
    )
    return _results(request, "degrees", [(value, "") for value in values])


@api_view(["GET"])
@permission_classes([AllowAny])
def locations(request):
    personal = (
        PersonalDetail.objects.filter(resume__user=request.user).filter(
            Q(city__icontains=request.query_params.get("q", ""))
            | Q(country__icontains=request.query_params.get("q", ""))
        )
        if request.user.is_authenticated
        else []
    )
    database_values = []
    for detail in personal[:20]:
        label = ", ".join(part for part in [detail.city, detail.country] if part)
        if label:
            database_values.append((label, ""))
    return _results(request, "locations", database_values)
