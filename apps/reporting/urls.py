from django.urls import path

from .staff_sales import StaffSalesDetailView
from .staff_summary import StaffSalesSummaryView
from .views import DailyReportView, DashboardView, StaffReportView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="admin-dashboard"),
    path("reports/daily/", DailyReportView.as_view(), name="admin-report-daily"),
    path("reports/staff/", StaffReportView.as_view(), name="admin-report-staff"),
    path(
        "reports/staff-summary/",
        StaffSalesSummaryView.as_view(),
        name="admin-report-staff-summary",
    ),
    path(
        "reports/staff-sales/",
        StaffSalesDetailView.as_view(),
        name="admin-report-staff-sales",
    ),
]
