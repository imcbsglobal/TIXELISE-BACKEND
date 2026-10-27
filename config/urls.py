from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/platform/", include("apps.platform_admin.urls")),
    path("api/v1/admin/", include("apps.events.urls")),
    path("api/v1/admin/", include("apps.catalog.urls")),
    path("api/v1/admin/", include("apps.staff.urls")),
    path("api/v1/admin/", include("apps.assignments.urls")),
    path("api/v1/admin/", include("apps.ticketing.urls")),
    path("api/v1/admin/", include("apps.sales.admin_urls")),
    path("api/v1/admin/", include("apps.audit.urls")),
    path("api/v1/admin/", include("apps.reporting.urls")),
    path("api/v1/pos/", include("apps.sales.pos_urls")),
]
