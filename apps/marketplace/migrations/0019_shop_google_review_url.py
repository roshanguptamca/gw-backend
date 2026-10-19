from django.db import migrations, models


def seed_rishi_kitchen(apps, schema_editor):
    Shop = apps.get_model("marketplace", "Shop")
    Shop.objects.using(schema_editor.connection.alias).filter(
        slug="rishi-kitchen", google_review_url=""
    ).update(google_review_url="https://g.page/r/CY3aO82zczwuECA/review")


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0018_agentcheckout")]
    operations = [
        migrations.AddField(
            model_name="shop", name="google_review_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.RunPython(seed_rishi_kitchen, migrations.RunPython.noop),
    ]
