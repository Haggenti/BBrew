from django.core.management.base import BaseCommand

from bbrew.session_lifecycle import invalidate_sessions_on_startup


class Command(BaseCommand):
    help = "Invalidate all persisted user sessions."

    def handle(self, *args, **options):
        invalidate_sessions_on_startup()
        self.stdout.write(self.style.SUCCESS("All user sessions were invalidated."))
