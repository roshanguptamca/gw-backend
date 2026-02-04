import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "guidewisey.settings")
django.setup()

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"  # Hardcoded for now

if not User.objects.filter(username=ADMIN_USERNAME).exists():
    print("Creating superuser...")
    User.objects.create_superuser(
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD
    )
else:
    print("Superuser already exists")
