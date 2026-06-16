import apps.speaking_buddy.models
import django.db.models.deletion
from django.db import migrations, models


def mark_seed_avatars_full_body(apps, schema_editor):
    Buddy3DAvatar = apps.get_model("speaking_buddy", "Buddy3DAvatar")
    supported = {
        "skin_material": True,
        "hair_material": True,
        "eye_material": True,
        "hair_mesh": ["close-crop", "short", "medium", "long"],
        "beard_mesh": ["none", "short-beard"],
        "glasses_mesh": ["none", "classic-frames"],
        "body_type": ["balanced"],
        "outfit_style": ["casual", "smart-casual", "professional", "sport"],
    }
    Buddy3DAvatar.objects.filter(
        slug__in=["emma", "leo", "zara", "noah", "luna", "kai", "mila", "omar", "aria", "atlas"]
    ).update(
        base_skin_material_key="skin",
        base_hair_material_key="hair",
        supported_customizations=supported,
        has_full_body=True,
        has_hair=True,
        has_hands=True,
        has_feet=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('speaking_buddy', '0006_clear_placeholder_avatar_thumbnails'),
    ]

    operations = [
        migrations.AddField(
            model_name='buddy3davatar',
            name='base_hair_material_key',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='buddy3davatar',
            name='base_skin_material_key',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='buddy3davatar',
            name='has_feet',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='buddy3davatar',
            name='has_full_body',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='buddy3davatar',
            name='has_hair',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='buddy3davatar',
            name='has_hands',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='buddy3davatar',
            name='supported_customizations',
            field=models.JSONField(blank=True, default=apps.speaking_buddy.models.default_dict),
        ),
        migrations.AddField(
            model_name='buddygeneratedavatar',
            name='detected_features',
            field=models.JSONField(blank=True, default=apps.speaking_buddy.models.default_dict),
        ),
        migrations.AddField(
            model_name='buddygeneratedavatar',
            name='generation_method',
            field=models.CharField(choices=[('template', 'Template'), ('triposr', 'TripoSR'), ('instantmesh', 'InstantMesh'), ('pifuhd', 'PIFuHD'), ('pshuman', 'PSHuman'), ('mock', 'Mock')], default='template', max_length=20),
        ),
        migrations.AddField(
            model_name='buddygeneratedavatar',
            name='selected_base_avatar',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_variants', to='speaking_buddy.buddy3davatar'),
        ),
        migrations.AlterField(
            model_name='buddygeneratedavatar',
            name='status',
            field=models.CharField(choices=[('uploaded', 'Uploaded'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='uploaded', max_length=20),
        ),
        migrations.RunPython(mark_seed_avatars_full_body, migrations.RunPython.noop),
    ]
