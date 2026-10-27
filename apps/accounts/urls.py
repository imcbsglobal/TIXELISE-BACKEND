from django.urls import path

from .views import LoginView, LoginRefreshView, LogoutView, MeView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", LoginRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
]
