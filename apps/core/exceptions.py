import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class TixeliseAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "ERROR"
    default_detail = "Request failed."

    def __init__(self, detail=None, code=None, status_code=None):
        super().__init__(detail=detail, code=code)
        self.code = code or self.default_code
        if status_code is not None:
            self.status_code = status_code


class BadRequest(TixeliseAPIException):
    default_code = "BAD_REQUEST"
    default_detail = "Invalid request."


class Unauthorized(TixeliseAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "UNAUTHORIZED"
    default_detail = "Authentication credentials were not provided."


class TokenExpired(TixeliseAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "TOKEN_EXPIRED"
    default_detail = "Token has expired."


class InvalidToken(TixeliseAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "INVALID_TOKEN"
    default_detail = "Token is invalid."


class Forbidden(TixeliseAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "FORBIDDEN"
    default_detail = "You do not have permission to perform this action."


class TenantSuspended(TixeliseAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TENANT_SUSPENDED"
    default_detail = "This organization is suspended."


class TenantInactive(TixeliseAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TENANT_INACTIVE"
    default_detail = "This organization is inactive."


class MembershipInactive(TixeliseAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "MEMBERSHIP_INACTIVE"
    default_detail = "Your account is deactivated."


class NotTenantAdmin(Forbidden):
    default_code = "NOT_TENANT_ADMIN"
    default_detail = "Tenant administrator role required."


class NotPlatformAdmin(Forbidden):
    default_code = "NOT_PLATFORM_ADMIN"
    default_detail = "Platform administrator role required."


class NotPOSSStaff(Forbidden):
    default_code = "NOT_POS_STAFF"
    default_detail = "POS staff role required."


class AssignmentRequired(Forbidden):
    default_code = "ASSIGNMENT_REQUIRED"
    default_detail = "You are not assigned to sell tickets for this event."


class CategoryNotAllowed(Forbidden):
    default_code = "CATEGORY_NOT_ALLOWED"
    default_detail = "You are not permitted to sell this ticket category."


class EventNotSellable(TixeliseAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "EVENT_NOT_SELLABLE"
    default_detail = "This event is not currently sellable."


class SalesWindowClosed(TixeliseAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "SALES_WINDOW_CLOSED"
    default_detail = "The sales window for this event is closed."


class PriceUnavailable(TixeliseAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "PRICE_UNAVAILABLE"
    default_detail = "No active price is configured for this category."


class IdempotencyConflict(TixeliseAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "IDEMPOTENCY_CONFLICT"
    default_detail = "This idempotency key was used with a different request payload."


class NotFound(TixeliseAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "NOT_FOUND"
    default_detail = "Object not found."


class Conflict(TixeliseAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "CONFLICT"
    default_detail = "This record cannot be deleted because other records depend on it."


class NotImplementedYet(TixeliseAPIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    default_code = "NOT_IMPLEMENTED"
    default_detail = "This endpoint is not implemented yet."


# ---------------------------------------------------------------------------
# Serializes every error into the contract from MD §10.1:
# {"error": {"code": "...", "message": "..."}}
# ---------------------------------------------------------------------------
_CODE_MAP = {
    "authentication_failed": ("INVALID_TOKEN", status.HTTP_401_UNAUTHORIZED),
    "not_authenticated": ("UNAUTHORIZED", status.HTTP_401_UNAUTHORIZED),
    "token_not_valid": ("INVALID_TOKEN", status.HTTP_401_UNAUTHORIZED),
    "user_inactive": ("MEMBERSHIP_INACTIVE", status.HTTP_403_FORBIDDEN),
}


def api_exception_handler(exc, context):
    from rest_framework.views import exception_handler as drf_exception_handler

    if isinstance(exc, (ProtectedError, RestrictedError)):
        return Response(
            {
                "error": {
                    "code": "CONFLICT",
                    "message": "This record cannot be deleted because other records depend on it.",
                }
            },
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        if isinstance(exc, (Http404, DjangoPermissionDenied)):
            response = Response(
                {
                    "error": {
                        "code": "NOT_FOUND" if isinstance(exc, Http404) else "FORBIDDEN",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_404_NOT_FOUND
                if isinstance(exc, Http404)
                else status.HTTP_403_FORBIDDEN,
            )
            return response
        logger.exception(
            "Unhandled API exception (correlation handling continues)", exc_info=exc
        )
        response = Response(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        return response

    if isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = _flatten_validation_errors(exc.detail)
    else:
        raw_code = getattr(exc, "code", None) or getattr(exc, "default_code", "ERROR")
        code, mapped_status = _CODE_MAP.get(raw_code, (raw_code, None))
        message = getattr(exc, "detail", None) or "Request failed."
        if isinstance(message, (list, dict)):
            message = str(message)
        if mapped_status is not None:
            response.status_code = mapped_status

    response.data = {"error": {"code": code, "message": message}}
    return response


def _flatten_validation_errors(detail):
    if isinstance(detail, dict):
        parts = []
        for key, value in detail.items():
            parts.append(f"{key}: {_flatten_validation_errors(value)}")
        return "; ".join(parts)
    if isinstance(detail, list):
        return "; ".join(_flatten_validation_errors(item) for item in detail)
    return str(detail)
