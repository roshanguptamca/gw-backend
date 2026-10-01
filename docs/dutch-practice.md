# Free Dutch practice

Separate Django app `apps.dutch_practice`; session-authenticated API under `/api/dutch-practice/`.

## Available content

| Language difficulty | Reading | Writing | Listening | Speaking | KNM |
|---|---:|---:|---:|---:|---:|
| A1 | 20 sets | 20 sets | 20 sets | 20 sets | 20 sets |
| A2 | 20 sets | 20 sets | 20 sets | 20 sets | 20 sets |
| B1 | 20 sets | 20 sets | 20 sets | 20 sets | 20 sets |
| B2 | 20 sets | 20 sets | 20 sets | 20 sets | 20 sets |

400 selectable randomized practice sets. Each contains four questions selected from a pool of 16: 320 original draft questions total. There are 1,820 possible four-question selections per pool. The first 20 attempts in each pool have distinct question selections, verified by a test covering all 400 starts. Individual questions recur. After all possible selections are exhausted, selection may repeat, while avoiding the latest selection.

These are **short practice previews, not full official mock exams**. Full-length exam blueprints, broad passage coverage, review by qualified NT2 teachers, and calibrated difficulty are still required before claiming equivalence to an exam. A1 is informal foundational practice. Official KNM questions use A2 language; our A1/B1/B2 KNM pools are language adaptations of civic topics, not official KNM exam variants. KNM is currently text-based practice; full audiovisual KNM simulation is not implemented.

## Behaviour

- All questions, answer keys, attempt snapshots, responses and results reside in the server database. No frontend question bank is distributed. Catalog/history expose metadata only; an active question endpoint sends one question and its saved response.
- Only one active attempt per account, across categories and devices. PostgreSQL user-row locking serializes starts; a partial unique constraint enforces the rule. Attempts expire after two hours or can be abandoned.
- Randomized question selection and multiple-choice option order. Saved snapshots keep feedback stable when the live bank is edited.
- Reading/listening/KNM are automatically scored only on submission. Writing/speaking receive model responses and self-assessment criteria, with a null numeric score. Recording is optional, local and temporary; only speaking confirmation/notes are saved.
- Transcript-assisted listening is visibly labelled and recorded. Replays are allowed in this preview.
- Owner-scoped history is paginated, 20 rows per page. Completed results remain available to the owner. CSRF protection uses existing session authentication; all API/media responses are private and no-store.

## Clips in the database

64 original illustrated MP4 clips, approximately 5–27 seconds, with synthetic Dutch narration. Each listening question has a `PracticeMedia` foreign key. Binary content, MIME type, duration and checksum are stored in the database; attempt items retain the same media reference. Authenticated, owner-scoped URLs support HTTP byte ranges for video playback. No public media directory is served by the app.

Bundled MP4s are migration inputs, about 6 MB total. Normal database backups include the media. Generating new clips is an offline authoring operation, never a paid or live inference request. The application does not need Piper/ffmpeg installed at runtime. The optional `tools/generate_dutch_clips.py` requires Piper 1.8.0, ffmpeg and the Dutch Pim voice files. The model card identifies the dataset as CC0: https://huggingface.co/rhasspy/piper-voices/blob/main/nl/nl_NL/pim/medium/MODEL_CARD . Generated visuals and scripts are original; no PDF images, audio or question text are used.

## Installation and API

Run `python manage.py migrate`. Versioned migrations seed both banks and media; existing edits are preserved. New content should be added through a new bank/data migration or reviewed in Django admin. Do not edit released seed files/manifests in place. Media records are read-only in admin.

| Endpoint after `/api/dutch-practice/` | Method | Purpose |
|---|---|---|
| `catalog/` | GET | Levels, categories, availability and active attempt |
| `attempts/` | GET / POST | Paginated own history / start level, skill, mock_test 1–20 |
| `attempts/{id}/` | GET | Own attempt metadata and next unanswered position |
| `attempts/{id}/questions/{position}/` | GET / POST | One question / save choice, text or spoken confirmation |
| `attempts/{id}/questions/{position}/media/` | GET | Owned active/completed clip, including byte ranges |
| `attempts/{id}/submit/` | POST | Require all answers, score, persist and return feedback |
| `attempts/{id}/abandon/` | POST | Release active attempt |
| `attempts/{id}/result/` | GET | Feedback after completion only |

## Research and provenance

Four public teaching/curriculum PDFs were downloaded and read as background; no book/exam questions were copied or closely rewritten. A bulk download of 1,000 books was not performed. `dutch-practice-sources.json` records sources, rights notes and checksums. Some teaching PDFs contain third-party assets; none are imported. The KNM source is the revised curriculum effective 1 July 2025, not a question bank. The original source tags are pedagogical references, not claims that content is adapted or legally licensed from those sources.

Official pattern references: https://www.inburgeren.nl/examen-doen/inhoud-taalexamens-a2-b1-b2.jsp , https://www.staatsexamensnt2.nl/voorbereiden/hoe-ziet-het-examen-eruit , https://www.inburgeren.nl/examen-doen/inhoud-kennisexamens.jsp .

## Validation

`python manage.py test tests.dutch_practice --noinput` exercises the real migration chain and nine API/content tests, including 400 varied selections. Repository pytest uses `--nomigrations`, so the tests explicitly seed content when necessary. Frontend DOM tests cover one-question loading, all category controls, answer saving, result display, resuming, transcript assistance and microphone cleanup. Full browser/mobile visual and actual media/microphone playback testing remains required; the workspace disallows the sockets needed to launch Chromium.
