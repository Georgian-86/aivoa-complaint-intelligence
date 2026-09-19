"""ASGI entrypoint."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analytics, complaints, copilot, health, intake
from app.core.config import settings
from app.db.session import Base, engine

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
)
logger = logging.getLogger("aivoa")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.db.seed import seed_if_empty

    seeded = seed_if_empty()
    logger.info(
        "AIVOA API ready — db=%s ai=%s seeded=%s",
        engine.dialect.name,
        "groq" if settings.llm_enabled else "deterministic-fallback",
        seeded,
    )
    if not settings.llm_enabled:
        logger.warning(
            "GROQ_API_KEY is not set. The agent will run its deterministic engine so the "
            "product remains fully demonstrable, but extraction quality will be lower."
        )
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "AI-assisted customer complaint intake and triage for GMP-regulated API and "
        "finished-dosage-form manufacturing. LangGraph agent over Groq, FastAPI, SQLAlchemy."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time"],
)


@app.middleware("http")
async def timing(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error", "hint": str(exc)[:200] if settings.debug else None},
    )


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(intake.router, prefix=settings.api_prefix)
app.include_router(complaints.router, prefix=settings.api_prefix)
app.include_router(copilot.router, prefix=settings.api_prefix)
app.include_router(analytics.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
