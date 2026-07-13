from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


def health_check(request):
    checks = {"database": False, "cache": False}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        pass

    try:
        cache.set("health-check", "ok", timeout=10)
        checks["cache"] = cache.get("health-check") == "ok"
    except Exception:
        pass

    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unhealthy", "checks": checks},
        status=200 if healthy else 503,
    )


urlpatterns = [
    path("health/", health_check, name="health"),
    path("admin/", admin.site.urls),

    # API routes
    path("api/auth/", include("apps.users.urls")),
    path("api/", include("apps.workspaces.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.issues.urls")),

    # API docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

# Serve uploaded media from local disk in development. In production the files
# live in S3 (django-storages) and are served by the storage backend, so this
# has no effect there.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
