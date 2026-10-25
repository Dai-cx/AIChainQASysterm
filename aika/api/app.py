"""FastAPI application factory and lifespan."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aika.api.deps import _cached_qa_engine
from aika.api.routers import agents, conversations, graph, research
from aika.api.routers import status as status_routes
from aika.llm_client import load_dotenv

API_PREFIX = "/api"


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    engine = _cached_qa_engine()
    try:
        yield
    finally:
        engine.close()
        _cached_qa_engine.cache_clear()


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="AIQASYS API", version="0.1.0", lifespan=app_lifespan)
    # Registration order matches the single-router layout this package was split from.
    app.include_router(status_routes.router, prefix=API_PREFIX)
    app.include_router(agents.router, prefix=API_PREFIX)
    app.include_router(conversations.router, prefix=API_PREFIX)
    app.include_router(research.router, prefix=API_PREFIX)
    app.include_router(graph.router, prefix=API_PREFIX)
    return app


app = create_app()
