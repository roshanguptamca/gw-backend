# Dutch mock exam format verification

Verified **2026-10-04**, using the current public official pages and sample
introductions, not commercial preparation sites. All questions, scripts and
illustrations in our bank are original. Official sample questions/media are not
imported. These are independent practice simulations, not endorsed exams or
official-equivalent scoring.

## References

- DUO practice entry point: https://www.inburgeren.nl/examen-doen/oefenen.jsp
- DUO language components and timings:
  https://www.inburgeren.nl/examen-doen/inhoud-taalexamens-a2-b1-b2.jsp
- DUO KNM:
  https://www.inburgeren.nl/examen-doen/inhoud-kennisexamens.jsp
- NT2 detailed format and instruction-film transcripts:
  https://www.staatsexamensnt2.nl/voorbereiden/hoe-ziet-het-examen-eruit
- Current A2 reading sample introduction (25 questions / 65 minutes):
  https://oefenexamensduo.optimumassessment.com/spa/assessment-login/#/RV5Y
- Current A2 listening sample introduction (25 questions / 45 minutes):
  https://oefenexamensduo.optimumassessment.com/spa/assessment-login/#/NCJ5
- Current A2 speaking sample introduction (16 questions / 35 minutes; video,
  one-picture, two-picture and three-picture prompts):
  https://oefenexamensduo.optimumassessment.com/spa/assessment-login/#/DZ66
- Current 2025 KNM sample introduction: follow **Oefenexamen KNM 1** on the DUO
  practice page. It explicitly states that both the sample and real exam have
  **40 questions** and displays **45 minutes**.
- Current KNM curriculum (effective 2025-07-01):
  https://zoek.officielebekendmakingen.nl/stcrt-2024-15802.html
  confirms A2-language questions and eight themes. The mock selects five tasks
  per theme as an **author-chosen balance**, not a verified official weighting:
  work/income; manners/values/norms; housing; health; history/geography;
  institutions; government/rule of law; education/parenting.

The A2 sample introductions verify sample counts, not a promise that every live
language paper has exactly that count. No unsupported A2 per-task preparation
timing or replay restriction is presented as official.

## Comparison

| Component | Verified official pattern | Implemented practice | Limitations |
|---|---|---|---|
| A1 | No applicable official format verified | 12 reading, 12 listening, 4 writing or 8 speaking tasks | Explicitly **level-based practice**; times are author choices |
| A2 reading | Computer; texts and questions; sample 25; 65 min | 25 MCQs grouped with original texts; 65 min | Sample-based count; no official layout claim |
| A2 listening | Computer; films/listening texts; sample 25; 45 min | 25 MCQs with complete original Dutch recordings; 45 min | Audio/text instead of official audiovisual presentation; replays permitted and disclosed |
| A2 writing | Four tasks; practical short letters/forms; pen/paper; 40 min | Two messages and two forms; 40 min; rubric self-assessment | Typed instead of handwritten |
| A2 speaking | Computer; films and 1/2/3-picture tasks; sample 16; 35 min | Four original illustrated videos and four each of 1/2/3-diagram tasks; local recording; 35 min | Four-per-type distribution and preparation/response windows are author choices; schematic art, not natural footage |
| NT2 B1 reading | Six texts, 36 MCQs; 110 min | Six original grouped texts, 36 MCQs; 110 min | Text on screen instead of booklet; difficulty not externally calibrated |
| NT2 B2 reading | Six texts, 36 MCQs; 100 min | Six longer argumentative texts, 36 MCQs; 100 min | Same limitations |
| NT2 B1/B2 listening | About 40 tasks; ≥5 listening texts; 1–3 films with one task each; 90 min | 38 audio tasks in five groups plus two original illustrated video tasks; 90 min | Fixed 40; synthetic voices/illustrations, not natural multi-speaker videos |
| NT2 B1 writing | Eight sentence, two partial, two short writing tasks; 100 min | Exact task mix; rubric feedback; 100 min | Self-assessment, no official grade |
| NT2 B2 writing | 7–8 sentence, 1–2 short, 1–2 medium tasks; 100 min | Eight sentence, one short, one medium; 100 min | One selection within ranges; self-assessment |
| NT2 B1 speaking | Eight short (20s), eight medium (30s); approximately 25 min | Exact counts and response windows; 25 min | Preparation windows author-chosen; not official assessment |
| NT2 B2 speaking | Four short (20s), eight medium (30s), one long (120s); approx. 25 min | Exact counts/response windows; 25 min | Same limitation |
| KNM | Separate civic component; computer; themes; 40 questions; 45 min | One A2-language bank, 40 questions; 45 min | Audio/text scenarios rather than complete official audiovisual simulation |

NT2 reading covers audience/purpose, interpretation/relationships/conclusions,
and locating/combining information. NT2 listening gives **25 seconds** to read
before automatic playback, permits only one playback, no pause, and lets the
learner revisit/change answers without replaying. Our timed mode follows this
policy; short practice retains unrestricted replay/transcript assistance.
Autoplay browser blocking has an explicit start/recovery action. Refreshing does
not reset the server-recorded playback state.

Media interruptions are persisted and flagged in results as technically
unverified listening practice, rather than silently treated as a valid score.

NT2 speaking uses headphone prompts, microphone recording and beginning/end
signals. Our text-first prompts and preparation timers are declared deviations.
NT2 reading/writing allow only the specified Van Dale paper NT2 pocket dictionary;
listening/speaking do not allow a dictionary. The mock neither supplies a
dictionary nor claims to police outside resources.

Objective results report correct-answer counts and explanations, **not a
validated official pass threshold**. Writing and speaking provide model
responses and transparent self-assessment criteria for task completion,
organisation, vocabulary, grammar and (speaking) intelligibility. No AI request,
payment or pass prediction is required at exam time.

## Content review status

The expanded bank is authored offline from original scenarios. Automated review
checks IDs, exact duplicates, answer uniqueness, task mix, sufficient complete
sets, media checksums, and snapshot consistency. Topic and level metadata are
included. Reusable authoring structures mean some question/task patterns recur;
the bank is not represented as professionally calibrated. Qualified native
Dutch/NT2 teacher review is still required before claiming exam-equivalent
difficulty or assessment. Existing short practice banks and released media are
immutable and remain accessible separately.

## Reproducing checks

Run Django checks/tests from the backend with its dependencies installed.
Use `DB_NAME=` for documented local SQLite operation.

```sh
DB_NAME= python manage.py check
DB_NAME= python manage.py makemigrations --check --dry-run
DB_NAME= python manage.py test tests.dutch_practice --noinput
RUN_DUTCH_BROWSER_TESTS=1 DUTCH_FRONTEND_DIR=../gw-frontend DB_NAME= \
  python manage.py test tests.dutch_practice.test_browser --noinput
```

The opt-in browser test uses an isolated Django test user/session and actual
frontend scripts/API. Playwright Chromium must be installed in the frontend.
It checks mobile reading/resume, all A2 speaking visual types, full submissions,
saved results, complete listening playback and fake-device microphone encoding.
