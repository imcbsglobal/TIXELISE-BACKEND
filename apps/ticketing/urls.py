from django.urls import path

from .views import TicketDetailView, TicketListView, TicketReprintView

urlpatterns = [
    path("tickets/", TicketListView.as_view(), name="admin-tickets"),
    path("tickets/<uuid:pk>/", TicketDetailView.as_view(), name="admin-ticket-detail"),
    path("tickets/<uuid:pk>/reprint/", TicketReprintView.as_view(), name="admin-ticket-reprint"),
]
