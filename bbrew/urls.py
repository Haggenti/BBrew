from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from .auth_views import BBSLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", BBSLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("recipes.urls")),
]

static_patterns = staticfiles_urlpatterns()
for pattern in static_patterns:
    pattern.callback = login_not_required(pattern.callback)
urlpatterns += static_patterns
