from django.urls import path

from .views import AgentDetailView, AgentListCreateView, AgentStatusView

urlpatterns = [
    path("agents/", AgentListCreateView.as_view(), name="admin-agents"),
    path("agents/<int:pk>/", AgentDetailView.as_view(), name="admin-agent-detail"),
    path("agents/<int:pk>/status/", AgentStatusView.as_view(), name="admin-agent-status"),
]
