import copy
import hashlib
import itertools
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import APIException, ValidationError

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
    PracticeAttempt.objects.filter(user=user, status="active", expires_at__lte=timezone.now()).update(status="expired")


def signature(questions):
    codes = sorted(question.code for question in questions)
    return hashlib.sha256("|".join(codes).encode()).hexdigest()


def choose_questions(user, level, skill, mock_test):
    pool = list(PracticeQuestion.objects.filter(level=level, skill=skill, is_active=True).order_by("code"))
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


@transaction.atomic
def start_attempt(user, level, skill, mock_test):
    # Serialize starts across tabs/devices. A partial unique constraint provides a second DB guarantee.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    expire_attempts(user)
    active = PracticeAttempt.objects.filter(user=user, status="active").first()
    if active:
        raise ActiveAttemptConflict(
            {"detail": "Finish or abandon your active test first.", "attempt_id": str(active.id)}
        )
    selected = choose_questions(user, level, skill, mock_test)
    attempt = PracticeAttempt.objects.create(
        user=user,
        level=level,
        skill=skill,
        mock_test=mock_test,
        question_signature=signature(selected),
        expires_at=timezone.now() + timedelta(hours=2),
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
    )
    question = {key: item.snapshot[key] for key in allowed if key in item.snapshot}
    if item.media_id:
        question["mediaPath"] = f"/dutch-practice/attempts/{item.attempt_id}/questions/{item.position}/media/"
        question["audioMode"] = "generated-video"
    return {
        "position": item.position,
        "question": question,
        "response": item.response,
        "answered": item.answered_at is not None,
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
        "assessment": "automatic" if attempt.skill in ("reading", "listening", "knm") else "self_assessment",
        "next_position": attempt.items.filter(answered_at__isnull=True).values_list("position", flat=True).first(),
        "format": "short-practice-preview",
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
        if not data.get("text", "").strip():
            raise ValidationError("Write an answer before continuing.")
        response = {"text": data["text"]}
    else:
        if not data.get("spoken"):
            raise ValidationError("Confirm that you answered aloud before continuing.")
        response = {"spoken": True, "text": data.get("text", "")}
    item.response = response
    item.answered_at = timezone.now()
    item.save(update_fields=["response", "answered_at"])
    return item


def submit_attempt(attempt):
    if attempt.status == "completed":
        return  # idempotent retries cannot create another completion or alter the result
    require_active(attempt)
    items = list(attempt.items.all())
    if not items or any(item.answered_at is None for item in items):
        raise ValidationError("Answer all questions before submitting.")
    if attempt.skill in ("reading", "listening", "knm"):
        attempt.score = sum(item.response.get("choice") == item.snapshot["answer"] for item in items)
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
            {"modelAnswer": question["modelAnswer"], "criteria": question["criteria"]}
            if attempt.skill in ("writing", "speaking")
            else {
                "correct_choice": question["answer"],
                "explanation": question["explanation"],
                "correct": item.response.get("choice") == question["answer"],
            }
        )
        items.append({**public_question(item), "feedback": feedback})
    return {"attempt": summary(attempt), "items": items}
