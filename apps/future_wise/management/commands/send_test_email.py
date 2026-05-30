"""
Management command: python manage.py send_test_email <email>

Sends a test reminder email directly via the configured SMTP backend.
Use this to verify end-to-end email delivery without waiting for a
scheduled reminder to become due.

Examples:
    python manage.py send_test_email you@example.com
    make test-email EMAIL=you@example.com
"""

from django.core.management.base import BaseCommand, CommandError

from apps.future_wise.email_service import BrevoDeliveryError, BrevoEmailService


class Command(BaseCommand):
    help = "Send a test reminder email to verify SMTP is working"

    def add_arguments(self, parser):
        parser.add_argument("email", help="Recipient email address")

    def handle(self, *args, **options):
        to_email = options["email"]

        self.stdout.write(f"Sending test email to {to_email} ...")

        try:

            class _FakeReminder:
                email = to_email
                subject = "✅ FutureWise — SMTP test"
                message = "This is a test email to verify your SMTP configuration is working."
                tier = "free"
                brand_name = "FutureWise"

            BrevoEmailService().send_reminder_email(_FakeReminder())
            self.stdout.write(self.style.SUCCESS(f"✅ Test email sent to {to_email}"))

        except BrevoDeliveryError as exc:
            raise CommandError(f"❌ Delivery failed: {exc}") from exc
