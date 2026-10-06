from django.contrib.sessions.models import Session


def invalidate_sessions_on_startup():
    Session.objects.all().delete()
