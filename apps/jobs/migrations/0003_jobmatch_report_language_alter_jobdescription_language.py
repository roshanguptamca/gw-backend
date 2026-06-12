from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("jobs", "0002_initial")]

    operations = [
        migrations.AlterField(
            model_name="jobdescription",
            name="language",
            field=models.CharField(choices=[("en", "English"), ("nl", "Dutch")], default="en", max_length=10),
        ),
        migrations.AddField(
            model_name="jobmatch",
            name="report_language",
            field=models.CharField(choices=[("en", "English"), ("nl", "Dutch")], default="en", max_length=10),
        ),
    ]
