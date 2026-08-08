from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import Base, engine
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router
from app.routes.extraction import router as extractions_router
from app.routes.graph import router as graph_router
from app.routes.misc import schemas_router, users_router
from app.routes.statements import router as statements_router
from app.routes.workspaces import router as workspaces_router

setup_logging(debug=False)

# Imports all models so database is setup on startup
import app.models.document  # noqa: F401
import app.models.run  # noqa: F401
import app.models.user  # noqa: F401
import app.models.workspace  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="OntoCurate API",
    version="0.1.0",
    description="Ontology-Guided Knowledge Extraction and Curation with LLMs",
    lifespan=lifespan,
    swagger_ui_parameters={"withCredentials": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(extractions_router)
app.include_router(graph_router)
app.include_router(statements_router)
app.include_router(workspaces_router)
app.include_router(users_router)
app.include_router(schemas_router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/openapi", tags=["meta"])
async def openapi():
    return app.openapi()
