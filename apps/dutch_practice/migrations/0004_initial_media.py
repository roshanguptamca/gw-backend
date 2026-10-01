import hashlib
import json
from pathlib import Path
from django.db import migrations


def seed(apps, schema_editor):
    Media = apps.get_model('dutch_practice', 'PracticeMedia')
    Question = apps.get_model('dutch_practice', 'PracticeQuestion')
    root = Path(__file__).resolve().parent.parent / 'data'
    manifest = json.loads((root / 'media-manifest.json').read_text())
    for clip in manifest['clips']:
        content = (root / 'media' / clip['file']).read_bytes()
        if hashlib.sha256(content).hexdigest() != clip['sha256']:
            raise ValueError('Practice clip checksum mismatch')
        media, _ = Media.objects.using(schema_editor.connection.alias).get_or_create(
            code=clip['question'] + '-' + clip['sha256'][:12],
            defaults={'content': content, 'sha256': clip['sha256'], 'duration_seconds': clip['duration_seconds'], 'mime_type': 'video/mp4'},
        )
        Question.objects.using(schema_editor.connection.alias).filter(code=clip['question'], media__isnull=True).update(media=media)


class Migration(migrations.Migration):
    dependencies = [('dutch_practice', '0003_practicemedia_attemptquestion_media_and_more')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
