import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("files", "0001_initial"),
        ("resumes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="personaldetail",
            name="include_photo",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="personaldetail",
            name="profile_photo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resume_profiles",
                to="files.userfile",
            ),
        ),
    ]
