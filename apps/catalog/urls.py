from django.urls import path

from .views import (
    EventPriceDetailView,
    EventPriceListCreateView,
    EventPriceStatusView,
    TicketCategoryDetailView,
    TicketCategoryListCreateView,
    TicketCategoryStatusView,
    TicketTemplateDetailView,
    TicketTemplateListCreateView,
)

urlpatterns = [
    path("categories/", TicketCategoryListCreateView.as_view(), name="admin-categories"),
    path("categories/<int:pk>/", TicketCategoryDetailView.as_view(), name="admin-category-detail"),
    path(
        "categories/<int:pk>/status/",
        TicketCategoryStatusView.as_view(),
        name="admin-category-status",
    ),
    path("prices/", EventPriceListCreateView.as_view(), name="admin-prices"),
    path("prices/<int:pk>/", EventPriceDetailView.as_view(), name="admin-price-detail"),
    path(
        "prices/<int:pk>/status/",
        EventPriceStatusView.as_view(),
        name="admin-price-status",
    ),
    path("ticket-templates/", TicketTemplateListCreateView.as_view(), name="admin-templates"),
    path(
        "ticket-templates/<int:pk>/",
        TicketTemplateDetailView.as_view(),
        name="admin-template-detail",
    ),
]
