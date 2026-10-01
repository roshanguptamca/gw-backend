import json
from pathlib import Path

from django.db import migrations


def seed_questions(apps, schema_editor):
    Question = apps.get_model("dutch_practice", "PracticeQuestion")
    # This versioned bank is immutable. Add later content in a separate bank/migration.
    path = Path(__file__).resolve().parent.parent / "data" / "initial-bank.json"
    bank = json.loads(path.read_text(encoding="utf-8"))
    for payload in bank["questions"]:
        Question.objects.using(schema_editor.connection.alias).get_or_create(
            code=payload["id"],
            defaults={"level": payload["level"], "skill": payload["skill"], "payload": payload,
                      "review_status": "draft", "is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [("dutch_practice", "0001_initial")]
    # Preserve user-edited questions if this data migration is reversed.
    operations = [migrations.RunPython(seed_questions, migrations.RunPython.noop)]
