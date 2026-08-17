"""The private SIDRA API.

Exposure posture for v0.1:

* Binds to ``127.0.0.1`` unless explicitly overridden, and the override
  requires an API token (enforced in :meth:`Settings.validate`).
* Bearer-token auth is applied whenever a token is configured, and is
  mandatory off-loopback.
* Bearer attempts are rate-limited before token comparison, so invalid-token
  floods cannot bypass request throttling; authenticated traffic keeps its
  separate normal API allowance.
* A per-client rate limit is applied to every API route; ``/health`` remains
  unauthenticated but cannot trigger unbounded local model health probes.
* Rate-limiter client state is bounded and fails closed for new clients when
  the active-client budget is saturated, so public-bind opt-in cannot turn
  source-IP churn into unbounded in-process memory growth.
* The health-probe budget is isolated from the authenticated ``/v1`` budget so
  an aggressive monitor cannot consume a client's normal API allowance.
* CORS is not enabled. Browsers on other origins cannot reach this.
"""

from __future__ import annotations

import hmac
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sidra_ai.api.audit import ApiAuditLog
from sidra_ai.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from sidra_ai.api.service import SidraService, get_service
from sidra_ai.config.settings import Settings, get_settings
from sidra_ai.ingestion.github_client import RepositoryNotAllowedError

_REPOSITORY_FORBIDDEN_DETAIL = "repository is not allowlisted"
_REQUEST_VALIDATION_DETAIL = "request validation failed"


class RateLimiter:
    """Fixed-window-per-client limiter with bounded client state.

    In-process only, which is correct for a single-node localhost service.
    A multi-node deployment needs a shared counter - noted in the roadmap
    rather than faked here.

    The client map is intentionally bounded. If the active-client budget is
    full, an unseen client is rejected rather than allocating more memory or
    evicting an active client's rate-limit state. Expired least-recently-used
    clients are reclaimed before that fail-closed decision.
    """

    def __init__(self, per_minute: int, *, max_clients: int = 2048) -> None:
        if max_clients <= 0:
            raise ValueError("max_clients must be positive")
        self.per_minute = per_minute
        self.max_clients = max_clients
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    @staticmethod
    def _prune_window(window: deque[float], now: float) -> None:
        while window and now - window[0] > 60.0:
            window.popleft()

    def _reclaim_expired_clients(self, now: float) -> None:
        """Drop expired LRU entries without scanning the full client map."""

        while self._hits:
            client, window = next(iter(self._hits.items()))
            self._prune_window(window, now)
            if window:
                break
            del self._hits[client]

    def check(self, client: str) -> bool:
        now = time.monotonic()
        window = self._hits.get(client)

        if window is None:
            self._reclaim_expired_clients(now)
            if len(self._hits) >= self.max_clients:
                return False
            window = deque()
            self._hits[client] = window
        else:
            self._hits.move_to_end(client)

        self._prune_window(window, now)
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True


def create_app(
    service: SidraService | None = None,
    settings: Settings | None = None,
    audit_log: ApiAuditLog | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    auth_limiter = RateLimiter(settings.rate_limit_per_minute)
    limiter = RateLimiter(settings.rate_limit_per_minute)
    health_limiter = RateLimiter(settings.rate_limit_per_minute)
    audit_log = audit_log or ApiAuditLog(Path(settings.data_dir) / "api_audit.jsonl")

    app = FastAPI(
        title="SIDRA AI",
        version="0.1.0",
        description=(
            "Private, local-first AI API. GitHub access is read-only; "
            "retrieved content is DATA, never instructions."
        ),
    )

    @app.exception_handler(RequestValidationError)
    def _request_validation_error(_: Request, _exc: RequestValidationError) -> JSONResponse:
        """Return a context-free 422 without reflecting request-controlled values."""

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _REQUEST_VALIDATION_DETAIL},
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

    def _check_rate_limit(request: Request, target: RateLimiter) -> None:
        client = request.client.host if request.client else "unknown"
        if not target.check(client):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
            )

    def auth_rate_limit(request: Request) -> None:
        _check_rate_limit(request, auth_limiter)

    def rate_limit(request: Request) -> None:
        _check_rate_limit(request, limiter)

    def health_rate_limit(request: Request) -> None:
        _check_rate_limit(request, health_limiter)

    def validate_repositories(current: SidraService, repositories: list[str] | None) -> None:
        if not repositories:
            return
        for repository in repositories:
            if not current.settings.is_repository_allowed(repository):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=_REPOSITORY_FORBIDDEN_DETAIL,
                )

    def record_audit(
        *,
        operation: str,
        input_chars: int,
        repositories: list[str] | None,
        response: dict[str, object],
    ) -> None:
        """Best-effort local audit without changing API availability.

        The sink accepts metadata only and cannot receive raw operator text,
        model output, auth headers or gate evidence through this call.
        """

        try:
            audit_log.record_response(
                operation=operation,
                input_chars=input_chars,
                requested_repositories=repositories or (),
                response=response,
            )
        except OSError:
            # A local disk failure must not turn a safe model response into an
            # HTTP error. The failure is deliberately not echoed to clients.
            pass

    guarded = [Depends(auth_rate_limit), Depends(authenticate), Depends(rate_limit)]

    # ------------------------------------------------------------------
    @app.get(
        "/health",
        response_model=HealthResponse,
        dependencies=[Depends(health_rate_limit)],
    )
    def health() -> Any:
        """Unauthenticated and minimal, but bounded before model health work."""

        return resolve_service().health()

    @app.post("/v1/retrieve", response_model=RetrieveResponse, dependencies=guarded)
    def retrieve(payload: RetrieveRequest) -> Any:
        """Search indexed DATA without invoking the local language model."""

        current = resolve_service()
        validate_repositories(current, payload.repositories)
        result = current.retrieve(
            payload.query, top_k=payload.top_k, repositories=payload.repositories
        )
        record_audit(
            operation="retrieve",
            input_chars=len(payload.query),
            repositories=payload.repositories,
            response=result,
        )
        return result

    @app.post("/v1/chat", response_model=ChatResponse, dependencies=guarded)
    def chat(payload: ChatRequest) -> Any:
        current = resolve_service()
        validate_repositories(current, payload.repositories)
        result = current.chat(
            payload.message, top_k=payload.top_k, repositories=payload.repositories
        )
        record_audit(
            operation="chat",
            input_chars=len(payload.message),
            repositories=payload.repositories,
            response=result,
        )
        return result

    @app.post("/v1/github/analyze", response_model=AnalyzeResponse, dependencies=guarded)
    def analyze(payload: AnalyzeRequest) -> Any:
        current = resolve_service()
        try:
            result = current.analyze_github(
                payload.repositories, force=payload.force, question=payload.question
            )
        except RepositoryNotAllowedError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_REPOSITORY_FORBIDDEN_DETAIL,
            ) from exc

        record_audit(
            operation="github_analyze",
            input_chars=len(payload.question),
            repositories=payload.repositories,
            response=result,
        )
        return result

    # ------------------------------------------------------------------
    @app.exception_handler(RepositoryNotAllowedError)
    def _not_allowed(_: Request, _exc: RepositoryNotAllowedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": _REPOSITORY_FORBIDDEN_DETAIL},
        )

    return app


app = None
"""Built lazily by :func:`get_app` so importing this module never reads env."""


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
