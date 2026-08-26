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
* FastAPI's generated interactive documentation routes are disabled, while
  the JSON schema route crosses the same auth/rate-limit boundary as private
  API routes.
* CORS is not enabled. Browsers on other origins cannot reach this.
* The one HTML route (``GET /``) is a constant, self-contained page behind the
  same auth and rate limit as the private API. It carries no index data and
  fetches nothing off this host, so serving it adds no origin, no asset host
  and no unauthenticated surface.
"""

from __future__ import annotations

import contextlib
import hmac
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response

from sidra_ai.api.artifacts import ArtifactNotFound, list_artifacts, read_artifact
from sidra_ai.api.audit import ApiAuditLog
from sidra_ai.api.refresher import BackgroundRefresher
from sidra_ai.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IndexResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from sidra_ai.api.service import SidraService, get_service
from sidra_ai.api.ui import ASK_PAGE
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
    # ``Settings.from_env()`` validates already, but embedding callers can
    # inject a Settings instance directly. Keep the private API boundary
    # fail-closed regardless of how configuration reached the app factory.
    settings.validate()
    auth_limiter = RateLimiter(settings.rate_limit_per_minute)
    limiter = RateLimiter(settings.rate_limit_per_minute)
    health_limiter = RateLimiter(settings.rate_limit_per_minute)
    audit_log = audit_log or ApiAuditLog(Path(settings.data_dir) / "api_audit.jsonl")

    # Started on startup, stopped on shutdown. Built before the app because
    # a lifespan handler has to be passed to the constructor.
    refresher_holder: dict[str, BackgroundRefresher] = {}

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        refresher_holder["refresher"].start()
        try:
            yield
        finally:
            refresher_holder["refresher"].stop()

    app = FastAPI(
        lifespan=lifespan,
        title="SIDRA AI",
        version="0.1.0",
        description=(
            "Private, local-first AI API. GitHub access is read-only; "
            "retrieved content is DATA, never instructions."
        ),
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    @app.exception_handler(RequestValidationError)
    def _request_validation_error(_: Request, _exc: RequestValidationError) -> JSONResponse:
        """Return context-free 422s without reflecting request-controlled input."""

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

    @app.get(
        "/",
        include_in_schema=False,
        response_class=HTMLResponse,
        dependencies=guarded,
    )
    def ask_page() -> Any:
        """Serve the one-page asking UI.

        It sits behind ``guarded`` like every other private route rather than
        next to ``/health``. That is the conservative choice and it has a
        cost worth naming: with a token configured, a browser cannot load
        this page by navigation, because navigation cannot carry an
        ``Authorization`` header. The page therefore works as a browser UI in
        the default posture (loopback, no token) and needs a header-capable
        client otherwise. Serving the shell unauthenticated would fix that,
        but it widens the unauthenticated surface, which is not a call this
        route should make on its own.

        No index data passes through here. The page is a constant, and the
        answer it shows is fetched by the browser from ``/v1/chat``, across
        the same auth and rate-limit boundary as any other client.
        """

        return HTMLResponse(ASK_PAGE)

    @app.get("/openapi.json", include_in_schema=False, dependencies=guarded)
    def openapi_schema() -> dict[str, Any]:
        """Expose schema only through the same private-API request boundary."""

        return app.openapi()

    # ------------------------------------------------------------------
    @app.get(
        "/health",
        response_model=HealthResponse,
        dependencies=[Depends(health_rate_limit)],
    )
    def health() -> Any:
        """Unauthenticated and minimal, but bounded before model health work."""

        return resolve_service().health()

    @app.get("/v1/index", response_model=IndexResponse, dependencies=guarded)
    def index() -> Any:
        """Report what is indexed. Authenticated, and content-free by design.

        Unlike ``/health`` this discloses repository names and counts, which
        is why it sits behind the same auth and rate limit as retrieval
        rather than next to the open liveness probe.
        """

        current = resolve_service()
        result = current.index_stats()
        record_audit(
            operation="index",
            input_chars=0,
            repositories=None,
            response=result,
        )
        # Read after recording, so a write that just failed is already
        # counted. An operator checking whether the sink is healthy should
        # not have to make a second call to see the answer.
        #
        # This sits here rather than on `/health` although the backlog item
        # allowed either: `/health` is unauthenticated, and "the audit log is
        # currently failing" is precisely what someone who wants unlogged
        # activity would like to learn without credentials.
        result["audit"] = audit_log.durability().to_dict()
        return result

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
        history = [(turn.question, turn.answer) for turn in payload.history or ()]
        result = current.chat(
            payload.message,
            top_k=payload.top_k,
            repositories=payload.repositories,
            history=history,
        )
        record_audit(
            operation="chat",
            # Replayed turns are model input too. Counting only the new message
            # would under-report a follow-up carrying eight prior turns as if it
            # were the same size as a first question. Lengths only; the audit
            # log never holds request content.
            input_chars=len(payload.message)
            + sum(len(question) + len(answer) for question, answer in history),
            repositories=payload.repositories,
            response=result,
        )
        return result

    @app.get("/v1/artifacts", dependencies=guarded)
    def artifacts() -> Any:
        """Name, size and time for each generated file. Never a preview.

        A generated deck is grounded in retrieved documents, so its body is
        the same DATA the index holds. A listing that carried an excerpt
        would put indexed content somewhere that reads as metadata, which is
        how it ends up in a log or a screenshot nobody screened.
        """

        current = resolve_service()
        found = [artifact.to_dict() for artifact in list_artifacts(current.settings.data_dir)]
        record_audit(
            operation="artifacts",
            input_chars=0,
            repositories=None,
            response={"count": len(found)},
        )
        return {"artifacts": found}

    @app.get("/v1/artifacts/{name}", dependencies=guarded)
    def artifact(name: str) -> Any:
        """Hand back one artifact as a download, never as a page here.

        The file holds generated markup. Rendering it at this origin would
        run it beside the field the operator types their token into, so it
        leaves as an attachment with sniffing disabled.
        """

        current = resolve_service()
        try:
            payload, filename = read_artifact(current.settings.data_dir, name)
        except ArtifactNotFound:
            # One status for "no such file" and for "not a name we allow", so
            # probing cannot map the directory by reading the difference.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found"
            ) from None
        record_audit(
            operation="artifact",
            input_chars=0,
            repositories=None,
            response={"bytes": len(payload)},
        )
        return Response(
            content=payload,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/v1/github/analyze", response_model=AnalyzeResponse, dependencies=guarded)
    def analyze(payload: AnalyzeRequest) -> Any:
        current = resolve_service()
        # Match chat/retrieve: reject the complete repository scope before the
        # ingestion pipeline can fetch or mutate the local RAG/state snapshot.
        validate_repositories(current, payload.repositories)
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

    # ------------------------------------------------------------------
    # Keep the index current without a human. Off unless configured; see
    # sidra_ai.api.refresher for why it never reaches the model.
    def _ingest_once() -> Any:
        return resolve_service().ingest_only()

    refresher = BackgroundRefresher(
        ingest=_ingest_once, interval_seconds=settings.ingest_interval_seconds
    )
    #: Exposed for tests and for the authenticated index endpoint. Not for
    #: /health, which is unauthenticated and must not disclose runtime state.
    app.state.refresher = refresher
    refresher_holder["refresher"] = refresher

    return app


app = None
"""Built lazily by :func:`get_app` so importing this module never reads env."""


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
