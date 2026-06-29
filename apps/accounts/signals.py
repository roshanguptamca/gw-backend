from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create a UserProfile whenever a new User is created.
    Staff and superuser accounts are auto-confirmed since they bypass the email flow.
    """
    if created:
        from .models import UserProfile

        profile, _ = UserProfile.objects.get_or_create(user=instance)
        if instance.is_staff or instance.is_superuser:
            profile.email_confirmed = True
            profile.save(update_fields=["email_confirmed"])
