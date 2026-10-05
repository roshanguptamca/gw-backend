import copy
import hashlib
import itertools
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework.exceptions import APIException, ValidationError

from .blueprints import BANK_VERSION, blueprint
from .models import AttemptQuestion, PracticeAttempt, PracticeQuestion, validate_payload

QUESTIONS_PER_TEST = 4
TEST_COUNT = 20


class ActiveAttemptConflict(APIException):
    status_code = 409
    default_code = "active_attempt"


class AttemptStateConflict(APIException):
    status_code = 409
    default_detail = "This attempt is no longer active."


def expire_attempts(user):
    expired = PracticeAttempt.objects.filter(user=user, status="active", expires_at__lte=timezone.now())
    for attempt in expired.filter(mode="mock"):
        with transaction.atomic():
            attempt = PracticeAttempt.objects.select_for_update().get(pk=attempt.pk)
            if attempt.status == "active":
                submit_attempt(attempt, timed_out=True)
    expired.filter(mode="practice").update(status="expired")


def signature(questions):
    codes = sorted(question.code for question in questions)
    return hashlib.sha256("|".join(codes).encode()).hexdigest()


def choose_questions(user, level, skill, mock_test):
    pool = list(
        PracticeQuestion.objects.filter(level=level, skill=skill, is_active=True)
        .filter(Q(payload__bankVersion__isnull=True) | ~Q(payload__bankVersion=BANK_VERSION))
        .order_by("code")
    )
    if len(pool) < 8:
        raise ValidationError("Not enough questions are available for this level and skill.")
    # Persisted per-user selection history works across devices and browsers.
    previous = set(
        PracticeAttempt.objects.filter(user=user, level=level, skill=skill).values_list("question_signature", flat=True)
    )
    rng = random.SystemRandom()
    rng.shuffle(pool)
    offset = (mock_test - 1) % len(pool)
    pool = pool[offset:] + pool[:offset]
    # Lazy combinations: stop at the first unseen selection; never load a large combinations list.
    for group in itertools.combinations(pool, QUESTIONS_PER_TEST):
        if signature(group) not in previous:
            return list(group)
    # After every possible selection is used, avoid the most recent set.
    latest = PracticeAttempt.objects.filter(user=user, level=level, skill=skill).first()
    for group in itertools.combinations(pool, QUESTIONS_PER_TEST):
        if not latest or signature(group) != latest.question_signature:
            return list(group)
    raise ValidationError("No alternate question selection is available.")


def complete_sets(level, skill):
    spec = blueprint(level, skill)
    if spec is None:
        return {}
    pool = PracticeQuestion.objects.filter(level=level, skill=skill, is_active=True, payload__bankVersion=BANK_VERSION)
    sets = {}
    for question in pool.order_by("code"):
        sets.setdefault(question.payload["setNumber"], []).append(question)
    from collections import Counter

    valid = {}
    for number, questions in sets.items():
        if number not in range(1, TEST_COUNT + 1):
            continue
        if len(questions) != spec["count"] or Counter(q.payload["taskType"] for q in questions) != Counter(spec["mix"]):
            continue
        if len({q.code for q in questions}) != len(questions):
            continue
        if skill in ("listening", "knm") and any(q.media_id is None for q in questions):
            continue
        if any(q.payload.get("mediaCode") and q.media_id is None for q in questions):
            continue
        if len({q.payload["groupId"] for q in questions}) != spec["groups"]:
            continue
        if "topics" in spec and Counter(q.payload.get("theme") for q in questions) != Counter(spec["topics"]):
            continue
        valid[number] = questions
    return valid


def choose_exam_questions(user, level, skill, mock_test):
    sets = complete_sets(level, skill)
    if len(sets) < TEST_COUNT:
        raise ValidationError(
            "A complete 20-set exam bank with all required media is not available. No shortened exam was created."
        )
    previous = list(
        PracticeAttempt.objects.filter(
            user=user, level=level, skill=skill, mode="mock", bank_version=BANK_VERSION
        ).values_list("question_signature", flat=True)[:20]
    )
    candidates = [number for number, questions in sets.items() if signature(questions) not in previous]
    if not candidates:
        candidates = [
            number for number, questions in sets.items() if not previous or signature(questions) != previous[0]
        ]
    selected_number = mock_test if mock_test in candidates else random.SystemRandom().choice(candidates)
    selected = sets[selected_number]
    groups = {}
    for question in selected:
        groups.setdefault(question.payload["groupId"], []).append(question)
    # Never separate a passage from its tasks or shuffle productive task sections.
    ordered = list(groups.values())
    if skill in ("reading", "knm"):
        random.SystemRandom().shuffle(ordered)
    return [question for group in ordered for question in sorted(group, key=lambda q: q.payload["withinGroup"])]


@transaction.atomic
def start_attempt(user, level, skill, mock_test, mode="practice"):
    # Serialize starts across tabs/devices. A partial unique constraint provides a second DB guarantee.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    expire_attempts(user)
    active = PracticeAttempt.objects.filter(user=user, status="active").first()
    if active:
        raise ActiveAttemptConflict(
            {"detail": "Finish or abandon your active test first.", "attempt_id": str(active.id)}
        )
    spec = blueprint(level, skill) if mode == "mock" else {}
    if mode == "mock" and spec is None:
        raise ValidationError("KNM is a standalone A2-language component, not a separate exam for every level.")
    selected = (
        choose_exam_questions(user, level, skill, mock_test)
        if mode == "mock"
        else choose_questions(user, level, skill, mock_test)
    )
    if mode == "mock":
        spec["selected_set"] = selected[0].payload["setNumber"]
    now = timezone.now()
    attempt = PracticeAttempt.objects.create(
        user=user,
        level=level,
        skill=skill,
        mock_test=mock_test,
        question_signature=signature(selected),
        expires_at=now + timedelta(minutes=spec["minutes"]) if mode == "mock" else now + timedelta(hours=2),
        mode=mode,
        bank_version=BANK_VERSION if mode == "mock" else "legacy-v2",
        blueprint=spec,
    )
    items = []
    rng = random.SystemRandom()
    for position, question in enumerate(selected):
        snapshot = copy.deepcopy(question.payload)
        validate_payload(snapshot, level, skill)
        if skill in ("reading", "listening", "knm"):
            options = list(enumerate(snapshot["options"]))
            rng.shuffle(options)
            snapshot["options"] = [text for _, text in options]
            snapshot["answer"] = next(
                index for index, (original, _) in enumerate(options) if original == snapshot["answer"]
            )
        items.append(AttemptQuestion(attempt=attempt, position=position, snapshot=snapshot, media_id=question.media_id))
    AttemptQuestion.objects.bulk_create(items)
    return attempt


def public_question(item):
    allowed = (
        "id",
        "level",
        "skill",
        "prompt",
        "text",
        "options",
        "transcript",
        "audioMode",
        "responseSeconds",
        "preparationSeconds",
        "taskType",
        "picturePanels",
    )
    allowed += ("groupId", "title", "topic", "target")
    question = {key: item.snapshot[key] for key in allowed if key in item.snapshot}
    if item.attempt.mode == "mock" and item.attempt.skill == "listening" and item.attempt.status != "completed":
        question.pop("transcript", None)
    if item.media_id:
        question["mediaPath"] = f"/dutch-practice/attempts/{item.attempt_id}/questions/{item.position}/media/"
        question["audioMode"] = "generated-video" if item.media.mime_type == "video/mp4" else "generated-audio"
    return {
        "position": item.position,
        "question": question,
        "response": item.response,
        "answered": item.answered_at is not None,
        "media_started_at": item.media_started_at,
    }


def summary(attempt):
    return {
        "id": str(attempt.id),
        "level": attempt.level,
        "skill": attempt.skill,
        "mock_test": attempt.mock_test,
        "status": attempt.status,
        "created_at": attempt.created_at,
        "expires_at": attempt.expires_at,
        "completed_at": attempt.completed_at,
        "score": attempt.score,
        "question_count": attempt.items.count(),
        "answered_count": attempt.items.filter(answered_at__isnull=False).count(),
        "assisted": attempt.assisted,
        "media_errors": attempt.items.filter(response__media_error=True).count(),
        "assessment": "automatic" if attempt.skill in ("reading", "listening", "knm") else "self_assessment",
        "next_position": (
            attempt.last_position
            if attempt.mode == "mock"
            else attempt.items.filter(answered_at__isnull=True).values_list("position", flat=True).first()
        ),
        "format": attempt.blueprint.get("family", "short-practice-preview"),
        "mode": attempt.mode,
        "bank_version": attempt.bank_version,
        "blueprint": attempt.blueprint,
        "server_now": timezone.now() if attempt.status == "active" else attempt.completed_at,
    }


def require_active(attempt):
    if attempt.status != "active" or attempt.expires_at <= timezone.now():
        raise AttemptStateConflict()


def save_answer(attempt, position, data):
    require_active(attempt)
    try:
        item = attempt.items.get(position=position)
    except AttemptQuestion.DoesNotExist:
        raise ValidationError("Invalid question position.")
    if attempt.skill in ("reading", "listening", "knm"):
        if "choice" not in data:
            raise ValidationError("Choose an answer.")
        response = {"choice": data["choice"]}
        if attempt.skill == "listening":
            # Once assisted, it stays assisted even if the learner later changes the answer.
            response["used_transcript"] = item.response.get("used_transcript", False) or data["used_transcript"]
    elif attempt.skill == "writing":
        if "text" not in data:
            raise ValidationError("Provide text; send an empty string to clear a timed writing draft.")
        if not data.get("text", "").strip() and attempt.mode != "mock":
            raise ValidationError("Write an answer before continuing.")
        response = {"text": data.get("text", "")}
    else:
        if "spoken" not in data:
            raise ValidationError("Provide spoken confirmation, or false for unconfirmed timed notes.")
        if not data.get("spoken") and attempt.mode != "mock":
            raise ValidationError("Confirm that you answered aloud before continuing.")
        response = {"spoken": bool(data.get("spoken")), "text": data.get("text", "")}
    if item.response.get("media_error"):
        response["media_error"] = True
    item.response = response
    answered = (
        bool(response["text"].strip())
        if attempt.skill == "writing"
        else response["spoken"] if attempt.skill == "speaking" else True
    )
    item.answered_at = timezone.now() if answered else None
    item.save(update_fields=["response", "answered_at"])
    return item


def submit_attempt(attempt, timed_out=False):
    if attempt.status == "completed":
        return  # idempotent retries cannot create another completion or alter the result
    if timed_out:
        if attempt.status != "active":
            raise AttemptStateConflict()
    else:
        require_active(attempt)
    items = list(attempt.items.all())
    if not items or (attempt.mode == "practice" and any(item.answered_at is None for item in items)):
        raise ValidationError("Answer all questions before submitting.")
    if attempt.skill in ("reading", "listening", "knm"):
        attempt.score = sum(
            item.answered_at is not None and item.response.get("choice") == item.snapshot["answer"] for item in items
        )
    attempt.assisted = any(item.response.get("used_transcript", False) for item in items)
    attempt.status = "completed"
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["score", "assisted", "status", "completed_at"])


def result(attempt):
    if attempt.status != "completed":
        raise AttemptStateConflict("Results are available only after submission.")
    items = []
    for item in attempt.items.all():
        question = item.snapshot
        feedback = (
            {"modelAnswer": question["modelAnswer"], "criteria": question["criteria"], "rubric": question.get("rubric")}
            if attempt.skill in ("writing", "speaking")
            else {
                "correct_choice": question["answer"],
                "explanation": question["explanation"],
                "correct": item.response.get("choice") == question["answer"],
            }
        )
        items.append({**public_question(item), "feedback": feedback})
    return {"attempt": summary(attempt), "items": items}
