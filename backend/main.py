"""FastAPI app entrypoint.

Wires the whole service together:
  - lifespan loads the in-RAM store (downloads artifacts from R2 if missing)
    and runs the events-table migration;
  - all routers mount under ``/api`` (each route requires a valid token);
  - the built SPA (frontend/dist) is served as static with an index.html
    catch-all for client-side routes, excluding ``/api`` and ``/docs``;
  - permissive CORS is enabled in development.

Routers and the auth/db modules are owned by other agents; their imports are
guarded so the core app still boots (and ``py_compile``s) if a module is not
yet present.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.store import store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# frontend/dist lives at the repo root, one level above the backend package.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Router module names to include under /api (owned by other agents).
_ROUTER_MODULES = ("search", "decisions", "facets", "events", "reports", "alj")

# MCP server (remote, streamable-HTTP) mounted at /mcp. Guarded so the core app
# still boots if the `mcp` SDK isn't installed. Calling streamable_http_app()
# here creates the session manager, whose lifespan we enter below.
try:
    from backend import mcp_server  # noqa: WPS433

    _MCP_APP = mcp_server.mcp.streamable_http_app()
    logger.info("MCP server initialised (mount at /mcp)")
except Exception:
    mcp_server = None  # type: ignore[assignment]
    _MCP_APP = None
    logger.warning("MCP server unavailable (mcp SDK missing?) — /mcp disabled", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.monotonic()

    from contextlib import AsyncExitStack

    async with AsyncExitStack() as stack:
        # The MCP session manager needs its lifespan running (a mounted ASGI
        # sub-app's lifespan does not run automatically).
        if _MCP_APP is not None:
            await stack.enter_async_context(mcp_server.mcp.session_manager.run())

        # Load indexes/records/metadata into RAM (downloads from R2 if missing).
        try:
            store.load()
        except Exception:
            logger.exception("store.load() failed at startup")

        # Create the events table (owned by backend.db).
        try:
            from backend import db  # noqa: WPS433 (guarded cross-agent import)
            db.create_all()
            logger.info("events table ready")
        except Exception:
            logger.exception("db.create_all() failed (analytics may be unavailable)")

        logger.info("Startup completed in %.1fs", time.monotonic() - t0)
        yield


app = FastAPI(title="Cert Layoff Search", lifespan=lifespan)

# Permissive CORS in development; locked-down deployments front this with their
# own origin policy (the SPA is same-origin in production).
if settings.ENV != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


def _include_routers(application: FastAPI) -> None:
    """Include every available router under /api. Each router defines its own
    prefix (``/api``) and token dependency per the contract; missing modules
    are skipped so the app still boots during parallel development."""
    import importlib

    for name in _ROUTER_MODULES:
        try:
            module = importlib.import_module(f"backend.routers.{name}")
        except Exception:
            logger.warning("router %s not available yet — skipping", name)
            continue
        router = getattr(module, "router", None)
        if router is None:
            logger.warning("router module %s has no 'router' attribute", name)
            continue
        application.include_router(router)
        logger.info("included router: %s", name)


_include_routers(app)

# Wire the MCP server in BEFORE the SPA catch-all so /mcp isn't swallowed by it.
# Starlette's Mount("/mcp") matches "/mcp/" but NOT bare "/mcp" (the canonical,
# no-slash URL clients and the claude.ai connector use) — bare "/mcp" would fall
# through to the SPA GET catch-all and 405 on POST. So lift FastMCP's exact
# Route("/mcp") in (matches "/mcp", any method), and add a Mount for the
# "/mcp/..." variants so a trailing slash also works.
if _MCP_APP is not None:
    from starlette.routing import Mount

    for _route in _MCP_APP.routes:  # the streamable-HTTP Route("/mcp")
        app.router.routes.append(_route)
    app.router.routes.append(
        Mount("/mcp", app=mcp_server.mcp.session_manager.handle_request)
    )
    logger.info("wired MCP server at /mcp (route + mount)")


@app.get("/healthz")
async def healthz():
    engine = store.engine
    stats = (store.metadata or {}).get("corpus_stats") or {}
    return {
        "status": "ok",
        "engine_loaded": engine is not None,
        "n_records": len(store.records),
        "n_decisions": stats.get("n_decisions"),
        "n_holdings": stats.get("n_holdings"),
        "embed_backend": settings.EMBED_BACKEND,
        "env": settings.ENV,
    }


# --- SPA static serving (guarded: dist may be absent during local dev) ---
if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        """Serve the SPA shell for any non-API client-side route. /api/* and
        /docs are matched by their own routes first (FastAPI route ordering),
        so they never reach this catch-all."""
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    logger.info("frontend/dist not found — SPA static serving disabled (dev mode)")
