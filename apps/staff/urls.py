from django.urls import path

from .views import (
    StaffActivateView,
    StaffDeactivateView,
    StaffDetailView,
    StaffListCreateView,
    StaffResetPasswordView,
)

urlpatterns = [
    path("staff/", StaffListCreateView.as_view(), name="admin-staff"),
    path("staff/<int:pk>/", StaffDetailView.as_view(), name="admin-staff-detail"),
    path("staff/<int:pk>/deactivate/", StaffDeactivateView.as_view(), name="admin-staff-deactivate"),
    path("staff/<int:pk>/activate/", StaffActivateView.as_view(), name="admin-staff-activate"),
    path(
        "staff/<int:pk>/reset-password/",
        StaffResetPasswordView.as_view(),
        name="admin-staff-reset-password",
    ),
]
