from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_api_key
from .config import settings
from .models import HealthResponse
from .routes.logs import router as logs_router
from .routes.server import router as server_router


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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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
app.include_router(server_router, dependencies=[Depends(require_api_key)])
app.include_router(logs_router, dependencies=[Depends(require_api_key)])
