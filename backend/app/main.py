from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.admin import router as admin_router
from app.api.bot import account_router
from app.api.bot import router as bot_router
from app.api.providers import router as providers_router
from app.api.routes import router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title="ZKS95 VPN API",
    version="0.1.0-dev",
    docs_url="/api/docs" if settings.enable_docs else None,
    openapi_url="/api/openapi.json" if settings.enable_docs else None,
    redoc_url=None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


@app.middleware("http")
async def security_headers_and_csrf(request: Request, call_next):
    # Every state-changing browser request, including login, requires the exact origin.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith(
        "/api/v1/internal/bot/"
    ):
        if request.headers.get("origin") != settings.public_url.rstrip("/"):
            return JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(router)
app.include_router(admin_router)
app.include_router(bot_router)
app.include_router(account_router)
app.include_router(providers_router)
