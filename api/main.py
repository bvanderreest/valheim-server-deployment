from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .auth import require_api_key
from .config import settings
from .models import HealthResponse
from .routes.config import router as config_router
from .routes.logs import router as logs_router
from .routes.metrics import router as metrics_router
from .routes.mods import router as mods_router
from .routes.modifiers import router as modifiers_router
from .routes.server import router as server_router
from .routes.updates import router as updates_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.api_enabled:
        raise RuntimeError(
            "API is disabled. Set API_ENABLED=true in your .env file to enable it."
        )
    if not settings.api_keys_list:
        raise RuntimeError(
            "No API keys configured. Set API_KEYS=your-key in your .env file."
        )
    # CORS: "*" with allow_credentials=True is forbidden by the CORS spec —
    # browsers reject the pair outright, so it is both broken AND a wildcard on
    # an API that can stop, update and reconfigure the server. Refuse to start
    # rather than ship a combination that looks permissive and works nowhere.
    if "*" in settings.cors_origins_list:
        raise RuntimeError(
            "CORS_ORIGINS=\"*\" is not allowed. Browsers reject a wildcard origin "
            "together with credentials, and this API can control the server. "
            "List your dashboard origin explicitly, e.g. "
            "CORS_ORIGINS=\"https://valheim.example.com\", or leave it empty for "
            "same-origin only."
        )
    if not settings.manager_script.exists():
        raise RuntimeError(
            f"Manager script not found: {settings.manager_script}. "
            "Run the API from the repository root directory."
        )

    yield


app = FastAPI(
    title="Game Server Management API",
    description=f"Managing {settings.server_label} ({settings.server_type})",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    # FastAPI does NOT gate the schema behind docs_url. Leaving openapi_url set
    # while docs are "disabled" served the full machine-readable route list to
    # anyone who could reach the port while hiding only the human UI (#79).
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # Auth is the X-API-Key header, never a cookie, so credentialed CORS buys
    # nothing and is what makes a wildcard origin dangerous.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type"],
)


# /health is unauthenticated — used by uptime monitors
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        server_type=settings.server_type,
        server_label=settings.server_label,
    )


# All routes in these routers require a valid API key
# ── Legacy unversioned mounts ─────────────────────────────────────────────────
# /v1 is canonical (see below). These bare paths are permanent aliases so no
# existing consumer breaks, but they are marked deprecated in the OpenAPI
# schema: "both work" is ambiguity, and a second implementer reading the spec
# must be able to see which surface is current.
app.include_router(server_router, dependencies=[Depends(require_api_key)], deprecated=True)
app.include_router(logs_router, dependencies=[Depends(require_api_key)], deprecated=True)
app.include_router(config_router, dependencies=[Depends(require_api_key)], deprecated=True)
app.include_router(mods_router, dependencies=[Depends(require_api_key)], deprecated=True)
app.include_router(modifiers_router, dependencies=[Depends(require_api_key)], deprecated=True)
app.include_router(updates_router, dependencies=[Depends(require_api_key)], deprecated=True)

# ── API versioning (#80) ──────────────────────────────────────────────────────
# Everything is also mounted under /v1. The bare paths stay as permanent,
# documented aliases so existing consumers do not break — this API is described
# as a reusable contract and is mirrored publicly, so an unversioned-only
# surface is not defensible. /health stays unversioned: it is an infrastructure
# probe, not part of the contract.
_V1 = "/v1"
CONTRACT_VERSION = "1.0.0"   # CoreHost Game Server API

for _r in (server_router, config_router, modifiers_router, mods_router, logs_router, updates_router):
    app.include_router(_r, prefix=_V1, dependencies=[Depends(require_api_key)])
app.include_router(metrics_router, prefix=_V1)


# /metrics is unauthenticated — consumable by Prometheus/Grafana without API key
app.include_router(metrics_router, deprecated=True)


# ── Web console (#33) ─────────────────────────────────────────────────────────
# Served from the same origin as the API, which is the point: no CORS, no second
# process, and the browser sends the key to the host it loaded from. The page
# itself is public — it is only markup. Everything it can DO still needs the
# X-API-Key, enforced per route.
_STATIC_DIR = Path(__file__).parent / "static"
_CONSOLE = _STATIC_DIR / "index.html"

if _CONSOLE.is_file():
    @app.get("/", include_in_schema=False)
    async def console() -> FileResponse:
        # no-store: the console changes with the API it talks to, and a stale
        # cached copy is worse than a slow load.
        return FileResponse(_CONSOLE, headers={"Cache-Control": "no-store"})
