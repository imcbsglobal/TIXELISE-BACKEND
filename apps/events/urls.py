from django.urls import path

from .views import EventDetailView, EventListCreateView, EventTransitionView

urlpatterns = [
    path("events/", EventListCreateView.as_view(), name="admin-events"),
    path("events/<int:pk>/", EventDetailView.as_view(), name="admin-event-detail"),
    path(
        "events/<int:pk>/<str:target_status>/",
        EventTransitionView.as_view(),
        name="admin-event-transition",
    ),
]
