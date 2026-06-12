"""
Management command: translate_questions_nl

Uses free Google Translate (via deep-translator) to generate Dutch (NL)
translations for all driving theory questions and answer options.

Usage:
    python manage.py translate_questions_nl                         # all topics
    python manage.py translate_questions_nl --topic road-users      # one topic
    python manage.py translate_questions_nl --batch-size 30         # tuning
    python manage.py translate_questions_nl --dry-run               # preview
    python manage.py translate_questions_nl --reset-topic road-users # re-translate

Resumable: questions that already have question_text_nl are skipped.
"""

import time
import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Translate driving theory questions/options to Dutch using Google Translate"

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic", type=str, default=None, help="Process only this topic slug. Omit for all topics."
        )
        parser.add_argument("--batch-size", type=int, default=30, help="Questions per translation batch (default 30)")
        parser.add_argument("--sleep", type=float, default=0.3, help="Seconds between batches (default 0.3)")
        parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
        parser.add_argument(
            "--reset-topic", type=str, default=None, help="Clear NL content for a topic then re-translate"
        )

    def _get_translator(self):
        try:
            from deep_translator import GoogleTranslator

            # No connectivity test — avoid burning a request at startup
            return GoogleTranslator(source="en", target="nl")
        except ImportError:
            raise CommandError("deep-translator not installed. Run: pip install deep-translator")

    def _translate_many(self, translator, texts):
        """Translate a list of strings with retry/backoff on rate limits."""
        if not texts:
            return []
        for attempt in range(5):
            try:
                results = translator.translate_batch(texts)
                return [r or "" for r in results]
            except Exception as e:
                if "too many requests" in str(e).lower() or "server error" in str(e).lower():
                    wait = 30 * (2**attempt)  # 30s, 60s, 120s, 240s, 480s
                    self.stdout.write(f"\n    Rate limit, waiting {wait}s…", ending="")
                    self.stdout.flush()
                    time.sleep(wait)
                else:
                    # Non-rate-limit: try one by one
                    out = []
                    for text in texts:
                        try:
                            out.append(translator.translate(text) or "")
                            time.sleep(0.3)
                        except Exception:
                            out.append("")
                    return out
        return ["" for _ in texts]

    def handle(self, *args, **options):
        from apps.driving_theory.models import DrivingQuestion, DrivingQuestionOption, DrivingTopic

        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        sleep_sec = options["sleep"]
        topic_slug = options["topic"]
        reset_slug = options["reset_topic"]

        # Optional reset
        if reset_slug:
            try:
                t = DrivingTopic.objects.get(slug=reset_slug)
            except DrivingTopic.DoesNotExist:
                raise CommandError(f"Topic not found: {reset_slug}")
            n = DrivingQuestion.objects.filter(topic=t).update(question_text_nl="")
            DrivingQuestionOption.objects.filter(question__topic=t).update(option_text_nl="")
            self.stdout.write(f"Reset {n} question NL translations for {reset_slug}")

        # Build queryset: untranslated, ordered by exam weight (highest first for mock tests)
        qs = (
            DrivingQuestion.objects.select_related("topic")
            .prefetch_related("options")
            .filter(is_active=True, question_text_nl="")
            .order_by("-topic__exam_weight", "topic__order", "id")
        )

        if topic_slug:
            try:
                topic = DrivingTopic.objects.get(slug=topic_slug)
            except DrivingTopic.DoesNotExist:
                raise CommandError(f"Topic not found: {topic_slug}")
            qs = qs.filter(topic=topic)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to translate — all questions already have Dutch!"))
            return

        self.stdout.write(f"Questions to translate: {total}")
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] — no changes will be saved"))

        translator = self._get_translator()
        self.stdout.write("Google Translate ready ✓")

        questions_list = list(qs)
        q_done = 0
        q_failed = 0

        for batch_start in range(0, len(questions_list), batch_size):
            batch = questions_list[batch_start : batch_start + batch_size]

            # Collect all strings to translate in one network call:
            # [q_text, opt1, opt2, opt3, opt4,  q_text, opt1, …]
            all_strings = []
            offsets = []  # (question_index, num_opts)
            for q in batch:
                opts = list(q.options.order_by("order", "id").values_list("option_text", flat=True))
                offsets.append((len(all_strings), len(opts)))
                all_strings.append(q.question_text)
                all_strings.extend(opts)

            progress = f"{batch_start + 1}–{min(batch_start + batch_size, total)}/{total}"
            self.stdout.write(f"  Batch {progress} … ", ending="")
            self.stdout.flush()

            try:
                translations = self._translate_many(translator, all_strings)
            except Exception as e:
                self.stderr.write(f"ERROR: {e}")
                q_failed += len(batch)
                time.sleep(2)
                continue

            # Write back
            for i, (q, (start_idx, num_opts)) in enumerate(zip(batch, offsets)):
                nl_q = translations[start_idx].strip() if start_idx < len(translations) else ""
                nl_opts = [
                    translations[start_idx + 1 + j].strip()
                    for j in range(num_opts)
                    if start_idx + 1 + j < len(translations)
                ]

                if not nl_q:
                    q_failed += 1
                    continue

                if not dry_run:
                    q.question_text_nl = nl_q
                    q.save(update_fields=["question_text_nl"])

                    current_opts = list(q.options.order_by("order", "id"))
                    for opt, nl_text in zip(current_opts, nl_opts):
                        if nl_text:
                            opt.option_text_nl = nl_text
                            opt.save(update_fields=["option_text_nl"])

                q_done += 1

            self.stdout.write(f"done (+{len(batch)})")

            if batch_start + batch_size < len(questions_list):
                time.sleep(sleep_sec)

        style = self.style.SUCCESS if q_failed == 0 else self.style.WARNING
        mode = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            style(f"\n{mode}Finished — {q_done} translated" + (f", {q_failed} failed" if q_failed else ""))
        )
