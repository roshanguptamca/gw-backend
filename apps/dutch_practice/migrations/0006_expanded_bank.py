import hashlib
import json
from pathlib import Path
from django.db import migrations


def seed(apps, schema_editor):
    Question = apps.get_model('dutch_practice', 'PracticeQuestion')
    Media = apps.get_model('dutch_practice', 'PracticeMedia')
    database = schema_editor.connection.alias
    root = Path(__file__).resolve().parent.parent / 'data'
    for question in json.loads((root / 'expanded-bank.json').read_text())['questions']:
        Question.objects.using(database).get_or_create(code=question['id'], defaults={
            'level': question['level'], 'skill': question['skill'], 'payload': question,
            'is_active': True, 'review_status': 'draft',
        })
    for clip in json.loads((root / 'expanded-media-manifest.json').read_text())['clips']:
        content = (root / 'media' / clip['file']).read_bytes()
        if hashlib.sha256(content).hexdigest() != clip['sha256']:
            raise ValueError('Practice clip checksum mismatch')
        media, _ = Media.objects.using(database).get_or_create(code=clip['question'] + '-' + clip['sha256'][:12], defaults={
            'content': content, 'sha256': clip['sha256'], 'duration_seconds': clip['duration_seconds'], 'mime_type': 'video/mp4',
        })
        Question.objects.using(database).filter(code=clip['question'], media__isnull=True).update(media=media)


class Migration(migrations.Migration):
    dependencies = [('dutch_practice', '0005_alter_practiceattempt_skill_and_more')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
