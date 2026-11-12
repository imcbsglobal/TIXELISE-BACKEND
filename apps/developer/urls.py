from django.urls import path

from .views import DeveloperDataSummaryView, DeveloperPurgeView

urlpatterns = [
    path(
        "developer/data-summary/",
        DeveloperDataSummaryView.as_view(),
        name="admin-developer-data-summary",
    ),
    path(
        "developer/delete-data/",
        DeveloperPurgeView.as_view(),
        name="admin-developer-delete-data",
    ),
]
