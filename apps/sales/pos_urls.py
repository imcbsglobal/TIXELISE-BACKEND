from django.urls import path

from apps.ticketing.print_profile import TicketPrintView
from apps.ticketing.views import TicketReprintView

from .pos_views import (
    POSCategoryListView,
    POSSaleCreateView,
    POSSaleHistoryView,
    POSTicketDetailView,
    POSEventListView,
)

urlpatterns = [
    path("events/", POSEventListView.as_view(), name="pos-events"),
    path(
        "events/<int:event_id>/categories/",
        POSCategoryListView.as_view(),
        name="pos-event-categories",
    ),
    path("sales/", POSSaleCreateView.as_view(), name="pos-sale-create"),
    path("sales/history/", POSSaleHistoryView.as_view(), name="pos-sale-history"),
    path("tickets/<uuid:pk>/", POSTicketDetailView.as_view(), name="pos-ticket-detail"),
    path("tickets/<uuid:pk>/reprint/", TicketReprintView.as_view(), name="pos-ticket-reprint"),
    path("tickets/<uuid:pk>/print/", TicketPrintView.as_view(), name="pos-ticket-print"),
]
