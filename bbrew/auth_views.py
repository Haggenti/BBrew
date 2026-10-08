import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView

logger = logging.getLogger(__name__)


def _version_parts(version):
    cleaned = version.strip().lstrip("vV")
    parts = cleaned.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _latest_release():
    request = Request(
        settings.BBS_RELEASES_API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "BBrew"},
    )
    with urlopen(request, timeout=2) as response:
        payload = json.load(response)
    return payload.get("tag_name", "").strip()


class BBSLoginView(LoginView):
    template_name = "registration/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        current = _version_parts(settings.BBS_VERSION)
        try:
            latest = _latest_release()
            latest_parts = _version_parts(latest)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            logger.warning("Unable to check for a newer BBrew release.")
            return response

        if current and latest_parts and latest_parts > current:
            messages.info(
                self.request,
                f"Une nouvelle version de BBrew est disponible : {latest}.",
            )
        return response
