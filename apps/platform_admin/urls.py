from django.urls import path

from .views import (
    TenantActivateView,
    TenantDeactivateView,
    TenantDetailView,
    TenantListCreateView,
    TenantLookupView,
    TenantSuspendView,
)

urlpatterns = [
    path("tenants/", TenantListCreateView.as_view(), name="platform-tenants"),
    path("tenants/lookup/", TenantLookupView.as_view(), name="platform-tenant-lookup"),
    path("tenants/<int:pk>/", TenantDetailView.as_view(), name="platform-tenant-detail"),
    path("tenants/<int:pk>/activate/", TenantActivateView.as_view(), name="platform-tenant-activate"),
    path("tenants/<int:pk>/suspend/", TenantSuspendView.as_view(), name="platform-tenant-suspend"),
    path(
        "tenants/<int:pk>/deactivate/",
        TenantDeactivateView.as_view(),
        name="platform-tenant-deactivate",
    ),
]
