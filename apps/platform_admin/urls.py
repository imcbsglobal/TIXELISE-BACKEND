from django.urls import path

from .views import (
    TenantActivateView,
    TenantCentralSyncView,
    TenantCurrencyOptionsView,
    TenantDeactivateView,
    TenantDetailView,
    TenantListCreateView,
    TenantLookupView,
    TenantSuspendView,
)

urlpatterns = [
    path("tenants/", TenantListCreateView.as_view(), name="platform-tenants"),
    path("tenants/lookup/", TenantLookupView.as_view(), name="platform-tenant-lookup"),
    path(
        "tenant-currencies/",
        TenantCurrencyOptionsView.as_view(),
        name="platform-tenant-currencies",
    ),
    path("tenants/<int:pk>/", TenantDetailView.as_view(), name="platform-tenant-detail"),
    path("tenants/<int:pk>/activate/", TenantActivateView.as_view(), name="platform-tenant-activate"),
    path("tenants/<int:pk>/suspend/", TenantSuspendView.as_view(), name="platform-tenant-suspend"),
    path(
        "tenants/<int:pk>/deactivate/",
        TenantDeactivateView.as_view(),
        name="platform-tenant-deactivate",
    ),
    path(
        "tenants/<int:pk>/sync-central/",
        TenantCentralSyncView.as_view(),
        name="platform-tenant-sync-central",
    ),
]
