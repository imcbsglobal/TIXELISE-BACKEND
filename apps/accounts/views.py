from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.services import record_audit

from .serializers import LoginSerializer, MeSerializer, build_tokens

User = get_user_model()


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        tenant = serializer.validated_data["tenant"]
        role = serializer.validated_data["role"]

        refresh, access = build_tokens(user, tenant, role)

        record_audit(
            actor=user,
            tenant=tenant,
            action="auth.login",
            target_type="user",
            target_id=user.id,
            metadata={"role": role},
        )

        return Response(
            {
                "refresh": refresh,
                "access": access,
                "role": role,
                "tenant": (
                    {
                        "id": tenant.id,
                        "code": tenant.code,
                        "name": tenant.name,
                        "timezone": tenant.timezone,
                        "currency": tenant.currency,
                    }
                    if tenant
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Stateless Phase 1: client discards tokens. Refresh-token
        # blacklisting can be added later with the token_blacklist app.
        return Response({"detail": "Signed out."}, status=status.HTTP_200_OK)


class LoginRefreshView(TokenRefreshView):
    """POST {refresh} -> rotated refresh + new access (claims preserved)."""
