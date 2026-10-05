# Free Dutch practice

Separate Django app `apps.dutch_practice`; session-authenticated API under `/api/dutch-practice/`.

## Complete timed mocks (bank v3)

The legacy four-question limit is retained **only for short practice**. Start
with `mode: "mock"` for a complete timed component, or `mode: "practice"` for the
original short sessions. Old clients default to practice. The catalog advertises
the applicable full formats and fails availability when any required set/media
is missing. Starting never falls back to a shorter exam.

| Level/component | Reading | Listening | Writing | Speaking | Complete sets |
|---|---:|---:|---:|---:|---:|
| A1 extended level practice | 12 | 12 | 4 | 8 | 20 per skill |
| A2 inburgering-style | 25 | 25 | 4 | 16 | 20 per skill |
| B1 / NT2 Programme I | 36 | 40 | 12 | 16 | 20 per skill |
| B2 / NT2 Programme II | 36 | 40 | 10 | 13 | 20 per skill |
| KNM standalone (A2 language) | — | — | — | — | 20 × 40 civic tasks |

There are **6,980 new tasks in 340 complete sets**, plus the immutable 320 legacy
questions. New records carry stable IDs, topic, target/difficulty, task type,
set number and bank version. Twenty complete authoring sets per component are
selected with recent-attempt avoidance; grouped texts/questions remain together.
Question wording and shuffled answer mappings are snapshotted. A selected set
may differ from the requested choice after recent repetition; `blueprint.selected_set`
records the actual authoring set.

Deadlines, selected order, last viewed position, answers and playback starts are
stored server-side. GET/HEAD endpoints never write, so they work in read-only
transactions. Elapsed deadlines are presented as completed timed results (or
expired short practice) from saved responses without changing the database.
The next owner POST persists expiry/completion under a write transaction;
starting a new attempt also finalizes any elapsed attempts before checking the
single-active-attempt constraint. Viewed timed positions are saved through
`POST attempts/{id}/questions/{position}/position/`, not question GET.
Expired timed attempts submit saved responses automatically;
unanswered objective tasks score zero. Timed NT2 listening has a 25-second
question preview and one playback; browser autoplay blocking is reported with a
manual recovery action. Playback reservations survive refresh, so a refreshed
fragment cannot be replayed. Short practice continues allowing transcript
assistance/replays. Audio failure is never reported as a successful listen.

The v3 seed migration imports the committed MP3/MP4 media with checksum validation
into the database. No TTS engine, external AI or paid call is needed while taking
an exam. The new bundle contains **1,285 files: 1,125 MP3s and 160 MP4s,
419,551,550 bytes (about 420 MB)**, in addition to legacy clips. Allow for this
database/storage/backup increase when subsequently planning deployment.
Both file checksums and bank-to-recording script hashes are verified by migration.
Offline authoring scripts are `tools/build_dutch_exam_bank.py` and
`tools/generate_dutch_exam_audio.py`; their output is versioned and immutable
after release. Do not modify a released bank or regenerate its assets in place.
Writing/speaking have explicit self-assessment rubrics and null numeric grades.
Local microphone recordings are temporary; only confirmation/notes persist.
Full A2 speaking includes original illustrated videos and 1/2/3-diagram prompts,
four of each as an author-chosen balance. KNM includes five tasks per each of
the eight current curriculum themes; this is not an official weighting.
Writing drafts and unconfirmed speaking notes persist without marking the task
answered. Clearing a full-mode writing response clears its answered state.

For dated official sources, format comparison, supported interactions and
remaining limitations, see [dutch-exam-alignment.md](dutch-exam-alignment.md).
This bank uses reusable original authoring structures, not 6,980 independently
teacher-calibrated questions. Exact duplicate tasks are checked; underlying
topics/principles and structures recur across sets. Native Dutch/NT2 review and
validated assessment remain outstanding.

Additional endpoint: `POST attempts/{id}/questions/{position}/playback/` records
the start of a fragment and rejects a second timed NT2 playback reservation.
Posting `{"failed": true}` instead records a technical interruption, which
remains visible in results even after the learner saves another answer.

## Available content

The following table describes **legacy short practice**, not the full formats above.

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
| `attempts/{id}/` | GET | Own metadata; last viewed timed task or next unanswered practice task |
| `attempts/{id}/questions/{position}/` | GET / POST | One question / save choice, text or spoken confirmation |
| `attempts/{id}/questions/{position}/media/` | GET | Owned active/completed clip, including byte ranges |
| `attempts/{id}/submit/` | POST | Score/persist feedback; short practice requires all answers |
| `attempts/{id}/questions/{position}/playback/` | POST | Reserve playback or record a technical media interruption |
| `attempts/{id}/abandon/` | POST | Release active attempt |
| `attempts/{id}/result/` | GET | Feedback after completion only |

## Research and provenance

Four public teaching/curriculum PDFs were downloaded and read as background; no book/exam questions were copied or closely rewritten. A bulk download of 1,000 books was not performed. `dutch-practice-sources.json` records sources, rights notes and checksums. Some teaching PDFs contain third-party assets; none are imported. The KNM source is the revised curriculum effective 1 July 2025, not a question bank. The original source tags are pedagogical references, not claims that content is adapted or legally licensed from those sources.

Official pattern references: https://www.inburgeren.nl/examen-doen/inhoud-taalexamens-a2-b1-b2.jsp , https://www.staatsexamensnt2.nl/voorbereiden/hoe-ziet-het-examen-eruit , https://www.inburgeren.nl/examen-doen/inhoud-kennisexamens.jsp .

## Validation

`python manage.py test tests.dutch_practice --noinput` exercises the real migration chain and nine API/content tests, including 400 varied selections. Repository pytest uses `--nomigrations`, so the tests explicitly seed content when necessary. Frontend DOM tests cover one-question loading, all category controls, answer saving, result display, resuming, transcript assistance and microphone cleanup. Full browser/mobile visual and actual media/microphone playback testing remains required; the workspace disallows the sockets needed to launch Chromium.
