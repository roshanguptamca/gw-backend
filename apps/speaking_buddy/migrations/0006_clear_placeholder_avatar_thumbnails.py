from django.db import migrations


def clear_missing_placeholder_thumbnails(apps, schema_editor):
    Buddy3DAvatar = apps.get_model("speaking_buddy", "Buddy3DAvatar")
    avatars = Buddy3DAvatar.objects.filter(
        thumbnail__startswith="/assets/buddy3d/",
        thumbnail__endswith=".webp",
    )
    avatars.update(thumbnail="", thumbnail_url="")


class Migration(migrations.Migration):
    dependencies = [
        ("speaking_buddy", "0005_buddy3davatar_listening_animation_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_missing_placeholder_thumbnails, migrations.RunPython.noop),
    ]
