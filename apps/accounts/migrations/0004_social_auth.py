import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_add_preferred_language"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="avatar_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="profile_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="timezone",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.CreateModel(
            name="UserAuthProvider",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("google", "Google"), ("facebook", "Facebook"), ("linkedin", "LinkedIn"), ("oidc", "OpenID Connect")], max_length=20)),
                ("provider_user_id", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("email_verified", models.BooleanField(default=False)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                ("avatar_url", models.URLField(blank=True, max_length=500)),
                ("locale", models.CharField(blank=True, max_length=35)),
                ("timezone", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_providers", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="OAuthTransaction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider", models.CharField(choices=[("google", "Google"), ("facebook", "Facebook"), ("linkedin", "LinkedIn"), ("oidc", "OpenID Connect")], max_length=20)),
                ("state_digest", models.CharField(max_length=64)),
                ("nonce", models.CharField(blank=True, max_length=128)),
                ("code_verifier", models.CharField(max_length=128)),
                ("redirect_uri", models.URLField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("link_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="oauth_transactions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="userauthprovider",
            constraint=models.UniqueConstraint(fields=("provider", "provider_user_id"), name="unique_provider_identity"),
        ),
        migrations.AddConstraint(
            model_name="userauthprovider",
            constraint=models.UniqueConstraint(fields=("user", "provider"), name="unique_user_provider"),
        ),
    ]
