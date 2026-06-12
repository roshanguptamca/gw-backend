# Career Suite English/Dutch Language Contract

Career Suite supports `en` and `nl`. Other language codes are rejected.

## Persisted language fields

| Resource | Field | Purpose |
|---|---|---|
| Resume | `locale` | CV preview and PDF/DOCX language |
| JobDescription | `language` | Source vacancy language |
| JobMatch | `report_language` | ATS recommendation language |
| OptimizedResume | `output_language` | Optimization output language |

The frontend UI language is independent from these fields.

## API examples

```json
PUT /api/resumes/123/
{"title": "Platform Engineer", "locale": "nl"}
```

```json
POST /api/job-match/analyze/
{"resume_id": 123, "job_description_id": 456, "language": "nl"}
```

```json
POST /api/job-match/789/optimize/
{
  "target_score": 90,
  "confirmed_skills": [],
  "declined_skills": [],
  "output_language": "nl"
}
```

## Export labels

| Section | English | Dutch |
|---|---|---|
| Summary | Professional Summary | Profiel |
| Experience | Work Experience | Werkervaring |
| Education | Education | Opleiding |
| Skills | Skills | Vaardigheden |
| Certifications | Certifications | Certificaten |
| Languages | Languages | Talen |
| References | References | Referenties |
| Current end date | Present | Heden |

Template layout, colors, fonts, and photo rules are language-independent.

## Cross-language matching

Common pairs are canonicalized, including communication/communicatie, leadership/leiderschap, project management/projectmanagement, customer service/klantenservice, sales/verkoop, accounting/boekhouding, and software development/softwareontwikkeling. Technical names such as React, Python, Django, TypeScript, Docker, and AWS remain unchanged.

## Migrations and verification

```bash
python manage.py migrate
.venv/bin/pytest -q
.venv/bin/python manage.py makemigrations --check --dry-run
```

Relevant migrations:

- `jobs.0003_jobmatch_report_language_alter_jobdescription_language`
- `resumes.0005_alter_resume_locale_optimizedresume_output_language`
