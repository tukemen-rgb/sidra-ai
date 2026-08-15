"""The private SIDRA API.

Exposure posture for v0.1:

* Binds to ``127.0.0.1`` unless explicitly overridden, and the override
  requires an API token (enforced in :meth:`Settings.validate`).
* Bearer-token auth is applied whenever a token is configured, and is
  mandatory off-loopback.
* A per-client rate limit is applied to every ``/v1`` route.
* CORS is not enabled. Browsers on other origins cannot reach this.
"""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from sidra_ai.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
)
from sidra_ai.api.service import SidraService, get_service
from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.ingestion.github_client import RepositoryNotAllowedError


class RateLimiter:
    """Fixed-window-per-client limiter.

    In-process only, which is correct for a single-node localhost service.
    A multi-node deployment needs a shared counter - noted in the roadmap
    rather than faked here.
    """

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str) -> bool:
        now = time.monotonic()
        window = self._hits[client]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True


def create_app(
    service: SidraService | None = None, settings: Settings | None = None
) -> FastAPI:
    settings = settings or get_settings()
    limiter = RateLimiter(settings.rate_limit_per_minute)

    app = FastAPI(
        title="SIDRA AI",
        version="0.1.0",
        description=(
            "Private, local-first AI API. GitHub access is read-only; "
            "retrieved content is DATA, never instructions."
        ),
    )

    def resolve_service() -> SidraService:
        return service or get_service()

    # ------------------------------------------------------------------
    def authenticate(request: Request) -> None:
        token = settings.api_token
        if not token:
            if not settings.is_localhost_only:
                # Defense in depth: Settings.validate already refuses this.
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API token required for non-loopback binding",
                )
            return

        header = request.headers.get("authorization", "")
        prefix = "Bearer "
        supplied = header[len(prefix) :] if header.startswith(prefix) else ""
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing bearer token",
            )

    def rate_limit(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.check(client):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
            )

    guarded = [Depends(authenticate), Depends(rate_limit)]

    # ------------------------------------------------------------------
    @app.get("/health", response_model=HealthResponse)
    def health() -> Any:
        """Unauthenticated: it reports no content and no secret values."""

        return resolve_service().health()

    @app.post("/v1/chat", response_model=ChatResponse, dependencies=guarded)
    def chat(payload: ChatRequest) -> Any:
        current = resolve_service()
        if payload.repositories:
            for repository in payload.repositories:
                if not current.settings.is_repository_allowed(repository):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"repository {repository!r} is not allowlisted",
                    )
        return current.chat(
            payload.message, top_k=payload.top_k, repositories=payload.repositories
        )

    @app.post("/v1/github/analyze", response_model=AnalyzeResponse, dependencies=guarded)
    def analyze(payload: AnalyzeRequest) -> Any:
        current = resolve_service()
        try:
            return current.analyze_github(
                payload.repositories, force=payload.force, question=payload.question
            )
        except RepositoryNotAllowedError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
            ) from exc

    # ------------------------------------------------------------------
    @app.exception_handler(RepositoryNotAllowedError)
    def _not_allowed(_: Request, exc: RepositoryNotAllowedError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    return app


app = None
"""Built lazily by :func:`get_app` so importing this module never reads env."""


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
