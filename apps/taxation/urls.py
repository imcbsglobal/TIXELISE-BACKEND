from django.urls import path

from .views import TaxSettingRefreshView, TaxSettingView

urlpatterns = [
    path("tax-settings/", TaxSettingView.as_view(), name="admin-tax-setting"),
    path(
        "tax-settings/refresh/",
        TaxSettingRefreshView.as_view(),
        name="admin-tax-setting-refresh",
    ),
]
