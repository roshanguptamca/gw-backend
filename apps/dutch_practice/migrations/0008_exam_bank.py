import hashlib
import json
from pathlib import Path

from django.db import migrations


def seed(apps, schema_editor):
    Question = apps.get_model("dutch_practice", "PracticeQuestion")
    Media = apps.get_model("dutch_practice", "PracticeMedia")
    database = schema_editor.connection.alias
    root = Path(__file__).resolve().parent.parent / "data"
    media_by_code = {}
    manifest = json.loads((root / "exam-media-v3.json").read_text())
    script_hashes = {clip["code"]: clip["script_sha256"] for clip in manifest["clips"]}
    for clip in manifest["clips"]:
        content = (root / "exam-media-v3" / clip["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != clip["sha256"]:
            raise ValueError(f"Exam media checksum mismatch: {clip['code']}")
        media, _ = Media.objects.using(database).get_or_create(
            code=clip["code"],
            defaults={
                "content": content,
                "sha256": clip["sha256"],
                "duration_seconds": clip["duration_seconds"],
                "mime_type": clip["mime_type"],
            },
        )
        media_by_code[clip["code"]] = media.pk
    bank = json.loads((root / "exam-bank-v3.json").read_text())
    for question in bank["questions"]:
        if "mediaCode" in question:
            if hashlib.sha256(question["transcript"].encode()).hexdigest() != script_hashes[question["mediaCode"]]:
                raise ValueError(f"Exam media script mismatch: {question['id']}")
        media_id = media_by_code[question["mediaCode"]] if "mediaCode" in question else None
        Question.objects.using(database).get_or_create(
            code=question["id"],
            defaults={
                "level": question["level"],
                "skill": question["skill"],
                "payload": question,
                "media_id": media_id,
                "review_status": "draft",
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("dutch_practice", "0007_attemptquestion_media_started_at_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
