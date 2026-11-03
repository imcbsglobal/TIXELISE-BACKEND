from django.urls import path

from .views import DailyReportView, DashboardView, StaffReportView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="admin-dashboard"),
    path("reports/daily/", DailyReportView.as_view(), name="admin-report-daily"),
    path("reports/staff/", StaffReportView.as_view(), name="admin-report-staff"),
]
