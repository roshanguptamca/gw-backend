from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("driving_theory", "0009_seed_v3_questions_prod"),
    ]

    operations = [
        migrations.AddField(
            model_name="drivingtopic",
            name="title_nl",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="drivingtopic",
            name="summary_nl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="drivinglesson",
            name="title_nl",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="drivinglesson",
            name="summary_nl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="drivinglessonsection",
            name="title_nl",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="drivinglessonsection",
            name="content_nl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="drivingquestion",
            name="question_text_nl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="drivingquestion",
            name="explanation_nl",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="drivingquestionoption",
            name="option_text_nl",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
