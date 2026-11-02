from django.core.management.base import BaseCommand, CommandError

from apps.securewise.runtime.trust import repository_tree_sha256


class Command(BaseCommand):
    help = "Print the SHA-256 digest used to approve exact SecureWise runtime build content."

    def add_arguments(self, parser):
        parser.add_argument("repository_path")

    def handle(self, *args, **options):
        try:
            digest = repository_tree_sha256(options["repository_path"])
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(digest)
