from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

logger = structlog.get_logger()

SKIP_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant slug from header and bind to request state."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path not in SKIP_PATHS:
            slug = request.headers.get("X-Tenant-Slug")
            if slug:
                request.state.tenant_slug = slug
                structlog.contextvars.bind_contextvars(tenant_slug=slug)

        response = await call_next(request)
        structlog.contextvars.clear_contextvars()
        return response
