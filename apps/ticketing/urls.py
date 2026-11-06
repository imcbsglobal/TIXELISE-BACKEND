from django.urls import path

from .print_profile import TicketPrintProfileView, TicketPrintView
from .views import TicketDetailView, TicketListView, TicketReprintView

urlpatterns = [
    path("tickets/", TicketListView.as_view(), name="admin-tickets"),
    path("tickets/<uuid:pk>/", TicketDetailView.as_view(), name="admin-ticket-detail"),
    path("tickets/<uuid:pk>/reprint/", TicketReprintView.as_view(), name="admin-ticket-reprint"),
    path("tickets/<uuid:pk>/print/", TicketPrintView.as_view(), name="admin-ticket-print"),
    path(
        "ticket-print/",
        TicketPrintProfileView.as_view(),
        name="admin-ticket-print-profile",
    ),
]
