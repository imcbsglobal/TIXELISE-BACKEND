from django.urls import path

from .views import AssignmentDetailView, AssignmentListCreateView, AssignmentRevokeView

urlpatterns = [
    path("assignments/", AssignmentListCreateView.as_view(), name="admin-assignments"),
    path(
        "assignments/<int:pk>/",
        AssignmentDetailView.as_view(),
        name="admin-assignment-detail",
    ),
    path(
        "assignments/<int:pk>/revoke/",
        AssignmentRevokeView.as_view(),
        name="admin-assignment-revoke",
    ),
]
