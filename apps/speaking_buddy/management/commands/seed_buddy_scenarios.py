from django.core.management.base import BaseCommand

from apps.speaking_buddy.services.scenario_seed import seed_scenarios


class Command(BaseCommand):
    help = "Seed the baseline Dutch and English AI Buddy practice scenarios."

    def handle(self, *args, **options):
        created, updated = seed_scenarios()
        self.stdout.write(self.style.SUCCESS(f"Scenarios seeded. created={created} updated={updated}"))
