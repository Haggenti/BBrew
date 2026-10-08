from django.http import HttpResponse
from django.template.loader import render_to_string


class NotFoundPageMiddleware:
    """Render the branded not-found page in development and production."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 404:
            return HttpResponse(
                render_to_string("404.html", request=request),
                status=404,
                content_type="text/html",
            )
        return response
