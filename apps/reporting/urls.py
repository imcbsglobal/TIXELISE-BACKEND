from django.urls import path

from .views import DashboardView, DailyReportView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="admin-dashboard"),
    path("reports/daily/", DailyReportView.as_view(), name="admin-report-daily"),
]
