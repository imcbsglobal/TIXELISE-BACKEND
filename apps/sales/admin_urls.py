from django.urls import path

from .admin_views import AdminSaleDetailView, AdminSaleListView

urlpatterns = [
    path("sales/", AdminSaleListView.as_view(), name="admin-sales"),
    path("sales/<int:pk>/", AdminSaleDetailView.as_view(), name="admin-sale-detail"),
]
