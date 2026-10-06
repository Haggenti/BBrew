from django.core.management.commands.runserver import Command as RunserverCommand

from bbrew.session_lifecycle import invalidate_sessions_on_startup


class Command(RunserverCommand):
    def handle(self, *args, **options):
        invalidate_sessions_on_startup()
        return super().handle(*args, **options)
