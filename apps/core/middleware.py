import uuid

from django.utils.deprecation import MiddlewareMixin

from .context import (
    clear_tenant_context,
    get_current_tenant_id,
    get_current_role,
    get_current_user_id,
    set_correlation_id,
    set_tenant_context,
)


class CorrelationIdMiddleware(MiddlewareMixin):
    """Assigns a correlation id to every request and echoes it on the response."""

    HEADER = "X-Correlation-ID"

    def process_request(self, request):
        meta_key = "HTTP_" + self.HEADER.upper().replace("-", "_")
        correlation_id = request.META.get(meta_key) or str(uuid.uuid4())
        set_correlation_id(correlation_id)
        request.correlation_id = correlation_id

    def process_response(self, request, response):
        correlation_id = getattr(request, "correlation_id", None)
        if correlation_id:
            response[self.HEADER] = correlation_id
        return response


class TenantContextMiddleware(MiddlewareMixin):
    """
    After JWT authentication (which sets the tenant context from verified token
    claims), this middleware copies it onto the request and guarantees the
    thread-local context is cleared at the end of every request/response cycle
    so pooled workers never leak one tenant's context into the next request.
    """

    def process_request(self, request):
        request.tenant_id = get_current_tenant_id()
        request.auth_role = get_current_role()
        request.auth_user_id = get_current_user_id()

    def process_response(self, request, response):
        clear_tenant_context()
        return response

    def process_exception(self, request, exception):
        clear_tenant_context()
