"""
app/main.py  —  FastAPI asosiy fayl.
"""
import sys
import asyncio

# Windows + Python 3.13 uchun asyncpg event loop fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.api.v1.auth import router as auth_router
from app.core.config import settings
from app.core.exceptions import EduSaaSException
from app.middleware.tenant import TenantMiddleware

try:
    from app.webhooks.bot import router as bot_webhook_router
    HAS_BOT = True
except Exception:
    HAS_BOT = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 EduSaaS v{settings.APP_VERSION} ishga tushdi")
    # Redis ulanishini tekshirish (birinchi chaqiruvda initsializatsiya)
    from app.core.invite_store import _get_redis
    r = await _get_redis()
    if r:
        print("✅ Redis ulandi")
    else:
        print("⚠️  Redis yo'q — in-memory fallback ishlatiladi (development)")
    if HAS_BOT:
        from app.webhooks.bot import setup_webhook
        await setup_webhook()
    yield
    print("👋 EduSaaS to'xtatildi")
    if HAS_BOT:
        from app.webhooks.bot import teardown_webhook
        await teardown_webhook()
    from app.core.invite_store import close_redis
    await close_redis()


app = FastAPI(
    title="EduSaaS API",
    version=settings.APP_VERSION,
    description="Ta'lim markazlari SaaS platformasi — FastAPI + PostgreSQL (schema-per-tenant)",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://*.ngrok-free.app",
        "https://*.ngrok.io",
        "https://mentor-me-omega.vercel.app",
        "https://*.vercel.app",
        *settings.allowed_origins_list,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Tenant Middleware ─────────────────────────────────────────────────
app.add_middleware(TenantMiddleware)

# ── Exception handlers ────────────────────────────────────────────────
@app.exception_handler(EduSaaSException)
async def edusaas_handler(request: Request, exc: EduSaaSException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )

@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {
            "code": "INTERNAL_ERROR",
            "message": str(exc),
        }},
    )

# ── Health ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}

# ── Routerlar ─────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(api_router,  prefix="/api/v1")

if HAS_BOT:
    app.include_router(bot_webhook_router)
