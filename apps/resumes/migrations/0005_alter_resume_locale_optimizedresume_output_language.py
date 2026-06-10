from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("resumes", "0004_education_duplicate_key_project_duplicate_key_and_more")]

    operations = [
        migrations.AlterField(
            model_name="resume",
            name="locale",
            field=models.CharField(choices=[("en", "English"), ("nl", "Dutch")], default="en", max_length=10),
        ),
        migrations.AddField(
            model_name="optimizedresume",
            name="output_language",
            field=models.CharField(choices=[("en", "English"), ("nl", "Dutch")], default="en", max_length=10),
        ),
    ]
