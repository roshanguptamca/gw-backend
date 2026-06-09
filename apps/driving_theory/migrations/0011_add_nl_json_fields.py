from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("driving_theory", "0010_add_nl_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="drivinglesson",
            name="common_mistakes_nl",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="drivinglesson",
            name="exam_tips_nl",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="drivinglesson",
            name="key_takeaways_nl",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="drivinglesson",
            name="learning_objectives_nl",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="drivinglessonsection",
            name="callout_boxes_nl",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="drivinglessonsection",
            name="examples_nl",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
