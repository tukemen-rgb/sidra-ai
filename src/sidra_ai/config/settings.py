"""Environment-driven settings.

Design rules for v0.1:

* Nothing here holds a secret value in source. Tokens are read from the
  environment at call time and never logged or serialized.
* The API binds to localhost. Exposing it beyond loopback requires an
  explicit opt-in *and* an API token, enforced in :meth:`Settings.validate`.
* The default model backend is local and needs no paid API.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse

#: Repositories SIDRA AI may read in v0.1. Anything else is refused by the
#: security gate as an unpermitted source.
DEFAULT_ALLOWED_REPOSITORIES: tuple[str, ...] = (
    "tukemen-rgb/site",
    "tukemen-rgb/creater-yard",
    "tukemen-rgb/Fg",
    "tukemen-rgb/marketing",
    "tukemen-rgb/sidra-ai",
)

#: Addresses considered loopback-only.
LOCALHOST_ADDRESSES: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})

#: Backends selectable in the verified v0.1 runtime. ``transformers`` remains
#: source-visible for future local-artifact work but is deliberately deferred
#: until runtime downloads are impossible.
LOCAL_MODEL_BACKENDS: frozenset[str] = frozenset({"echo", "ollama", "llama_cpp"})

#: v0.1 sends the optional read-only token only to GitHub's official API.
DEFAULT_GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_HOST = "api.github.com"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

#: Explicit non-loopback exposure needs more than a merely non-empty bearer
#: token. This is only a minimum accidental-weakness guard; operators should
#: still generate a random token rather than choosing a memorable phrase.
MIN_PUBLIC_API_TOKEN_CHARS = 24

#: Floor for an enabled background poller. GitHub's read quota is
#: shared with operator-driven requests, so a tight loop would spend
#: the budget the people using SIDRA need.
MIN_INGEST_INTERVAL_SECONDS = 60


class UnsafeConfigurationError(RuntimeError):
    """Raised when a configuration would weaken a v0.1 safety invariant."""


def _env_bool(name: str, default: bool = False) -> bool:
    """Read an explicit boolean without silently weakening safety controls.

    Typos and empty values fail closed instead of being coerced to ``False``.
    That matters for settings such as prompt-injection quarantine, where a
    malformed environment variable must never disable a protection.
    """

    raw = os.environ.get(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise UnsafeConfigurationError(
        f"{name} must be one of: 1, 0, true, false, yes, no, on, off"
    )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise UnsafeConfigurationError(f"{name} must be an integer") from exc


def _env_list(name: str, default: Iterable[str]) -> tuple[str, ...]:
    """Read a comma-separated list without broadening an explicit empty value."""

    raw = os.environ.get(name)
    if raw is None:
        return tuple(default)
    if not raw.strip():
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _validate_allowed_repositories(repositories: Iterable[str]) -> None:
    """Require one unambiguous GitHub ``owner/name`` identity per entry.

    API request schemas already reject duplicate logical repositories, but the
    configured default scope can bypass those schemas when GitHub analysis is
    invoked without an explicit repository list. Keep the configuration
    boundary equally strict so case-only duplicates cannot multiply ingestion
    work or create ambiguous authorization metadata.
    """

    seen: set[str] = set()
    for repository in repositories:
        owner, separator, name = repository.partition("/")
        if (
            repository != repository.strip()
            or any(char.isspace() for char in repository)
            or separator != "/"
            or not owner
            or not name
            or "/" in name
        ):
            raise UnsafeConfigurationError(
                "allowed repositories must use exactly one non-empty 'owner/name' identifier"
            )

        normalized = repository.casefold()
        if normalized in seen:
            raise UnsafeConfigurationError(
                "allowed repositories must not contain case-insensitive duplicates"
            )
        seen.add(normalized)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    # --- API surface -----------------------------------------------------
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allow_public_bind: bool = False
    """Must be explicitly enabled *and* paired with an API token."""

    rate_limit_per_minute: int = 60

    embedding_model_path: str = ""
    """Directory holding a local sentence-transformers model. Empty disables it.

    A path, never a model name: naming a model is what makes a process
    download one. Empty is a supported deployment - retrieval falls back to
    BM25, which is slower at finding paraphrases and just as available.
    """

    embedding_query_prefix: str = ""
    embedding_passage_prefix: str = ""
    """Asymmetric markers some retrieval models are trained with.

    e5 wants ``"query: "`` and ``"passage: "``. Left empty for symmetric
    models. Not inferred from the model directory, because that would break
    the first time somebody renames it.
    """

    ingest_interval_seconds: int = 0
    """Seconds between background differential ingestions. ``0`` disables it.

    Off by default: a server that starts polling GitHub because it was
    upgraded is a surprise, and the surprise is outbound traffic. Enabling it
    is a deliberate act. The floor below keeps an enabled poller from turning
    a typo into a rate-limit ban.
    """

    # --- Model backend ---------------------------------------------------
    model_backend: str = "echo"
    model_name: str = "sidra-local-v0"
    model_endpoint: str = ""
    """Base URL for Ollama / llama.cpp server backends. Local by default."""

    model_max_output_tokens: int = 512

    # --- GitHub ingestion (read-only) ------------------------------------
    github_api_base: str = DEFAULT_GITHUB_API_BASE
    allowed_repositories: tuple[str, ...] = DEFAULT_ALLOWED_REPOSITORIES
    github_request_timeout: float = 20.0
    ca_bundle: str = ""
    """PEM bundle to verify HTTPS against, or "" for the system default.

    Ambient environment routing is deliberately disabled for outbound
    requests so that credentials cannot leak through a workstation proxy,
    which also means ``SSL_CERT_FILE`` is not picked up. A network that
    terminates TLS - most corporate ones, and exactly where a self-hosted
    company assistant lives - therefore needs its CA named explicitly here.

    There is deliberately no option to skip verification. "It would not
    connect so I turned off the certificate check" is how a read-only client
    starts trusting whatever answers.
    """
    max_items_per_source: int = 50

    # --- Security gate ---------------------------------------------------
    max_input_bytes: int = 512 * 1024
    quarantine_prompt_injection: bool = True

    # --- Storage ---------------------------------------------------------
    data_dir: str = field(default=".sidra")

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        # Enforce GitHub network/credential boundaries even for callers that
        # construct Settings directly instead of using Settings.from_env().
        self._validate_github_api_base()
        self._validate_github_request_timeout()
        self._validate_ca_bundle()

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            host=os.environ.get("SIDRA_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST,
            port=_env_int("SIDRA_PORT", DEFAULT_PORT),
            allow_public_bind=_env_bool("SIDRA_ALLOW_PUBLIC_BIND", False),
            rate_limit_per_minute=_env_int("SIDRA_RATE_LIMIT_PER_MINUTE", 60),
            embedding_model_path=os.environ.get("SIDRA_EMBEDDING_MODEL_PATH", "").strip(),
            embedding_query_prefix=os.environ.get("SIDRA_EMBEDDING_QUERY_PREFIX", ""),
            embedding_passage_prefix=os.environ.get("SIDRA_EMBEDDING_PASSAGE_PREFIX", ""),
            ingest_interval_seconds=_env_int("SIDRA_INGEST_INTERVAL_SECONDS", 0),
            model_backend=os.environ.get("SIDRA_MODEL_BACKEND", "echo").strip()
            or "echo",
            model_name=os.environ.get("SIDRA_MODEL_NAME", "sidra-local-v0"),
            model_endpoint=os.environ.get("SIDRA_MODEL_ENDPOINT", ""),
            model_max_output_tokens=_env_int("SIDRA_MODEL_MAX_OUTPUT_TOKENS", 512),
            github_api_base=os.environ.get(
                "SIDRA_GITHUB_API_BASE", DEFAULT_GITHUB_API_BASE
            ).strip(),
            ca_bundle=os.environ.get("SIDRA_CA_BUNDLE", "").strip(),
            allowed_repositories=_env_list(
                "SIDRA_ALLOWED_REPOSITORIES", DEFAULT_ALLOWED_REPOSITORIES
            ),
            max_items_per_source=_env_int("SIDRA_MAX_ITEMS_PER_SOURCE", 50),
            max_input_bytes=_env_int("SIDRA_MAX_INPUT_BYTES", 512 * 1024),
            quarantine_prompt_injection=_env_bool(
                "SIDRA_QUARANTINE_PROMPT_INJECTION", True
            ),
            data_dir=os.environ.get("SIDRA_DATA_DIR", ".sidra"),
        )
        settings.validate()
        return settings

    # ------------------------------------------------------------------
    @property
    def is_localhost_only(self) -> bool:
        return self.host in LOCALHOST_ADDRESSES

    @property
    def api_token(self) -> str:
        """Read the API token from the environment on every access.

        Deliberately not a stored field: it must not end up in ``repr``,
        logs, or any serialized settings dump.
        """

        return os.environ.get("SIDRA_API_TOKEN", "")

    @property
    def github_token(self) -> str:
        """Read-only GitHub token, if configured.

        v0.1 works without it against public repositories; a token only
        raises rate limits and grants read access to private repositories.
        It is never used for write requests - the client has no write path.
        """

        return os.environ.get("SIDRA_GITHUB_TOKEN", "")

    def is_repository_allowed(self, repository: str) -> bool:
        return repository.lower() in {r.lower() for r in self.allowed_repositories}

    def _validate_ca_bundle(self) -> None:
        if not self.ca_bundle:
            return
        path = Path(self.ca_bundle)
        if not path.is_file():
            raise UnsafeConfigurationError(
                f"SIDRA_CA_BUNDLE points at {self.ca_bundle!r}, which is not a "
                "readable file. Failing closed rather than silently falling "
                "back to the default trust store"
            )

    def _validate_github_request_timeout(self) -> None:
        """Keep read-only GitHub calls on a finite positive deadline."""

        timeout = self.github_request_timeout
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise UnsafeConfigurationError(
                "github_request_timeout must be a finite positive number"
            )

    def _validate_github_api_base(self) -> None:
        """Pin authenticated GitHub ingestion to the official HTTPS origin.

        The read-only token raises API limits and can read private repositories.
        Allowing an arbitrary configured API base would therefore turn a typo or
        configuration injection into credential exfiltration, even though the
        client only issues GET requests.
        """

        message = (
            "SIDRA_GITHUB_API_BASE must be the official "
            "https://api.github.com origin in v0.1"
        )
        raw = self.github_api_base.strip()
        try:
            parsed = urlparse(raw)
            port = parsed.port
        except ValueError as exc:
            raise UnsafeConfigurationError(message) from exc

        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() != GITHUB_API_HOST
            or port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise UnsafeConfigurationError(message)

    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Enforce the v0.1 safety invariants."""

        self._validate_github_api_base()
        self._validate_github_request_timeout()

        if self.port < 1 or self.port > 65535:
            raise UnsafeConfigurationError("port out of range")

        if self.rate_limit_per_minute <= 0:
            raise UnsafeConfigurationError("rate_limit_per_minute must be positive")

        if self.ingest_interval_seconds < 0:
            raise UnsafeConfigurationError(
                "ingest_interval_seconds must not be negative"
            )
        if 0 < self.ingest_interval_seconds < MIN_INGEST_INTERVAL_SECONDS:
            # Refuse rather than clamp: silently running 60x more often than
            # asked is worse than refusing to start.
            raise UnsafeConfigurationError(
                "ingest_interval_seconds must be 0 (disabled) or at least "
                f"{MIN_INGEST_INTERVAL_SECONDS}"
            )

        if not self.data_dir.strip():
            raise UnsafeConfigurationError("data_dir must not be empty or whitespace")

        if not self.is_localhost_only:
            if not self.allow_public_bind:
                raise UnsafeConfigurationError(
                    f"refusing to bind non-loopback host {self.host!r}: set "
                    "SIDRA_ALLOW_PUBLIC_BIND=true only after authentication and "
                    "rate limiting are reviewed"
                )
            token = self.api_token
            if not token:
                raise UnsafeConfigurationError(
                    "non-loopback bind requires SIDRA_API_TOKEN to be set"
                )
            if len(token) < MIN_PUBLIC_API_TOKEN_CHARS or not all(
                0x21 <= ord(char) <= 0x7E for char in token
            ):
                raise UnsafeConfigurationError(
                    "non-loopback bind requires SIDRA_API_TOKEN to contain at least "
                    f"{MIN_PUBLIC_API_TOKEN_CHARS} visible ASCII characters"
                )

        if self.model_backend not in LOCAL_MODEL_BACKENDS:
            raise UnsafeConfigurationError(
                f"model backend {self.model_backend!r} is not a local backend; "
                f"verified v0.1 allows {sorted(LOCAL_MODEL_BACKENDS)}"
            )

        if self.model_max_output_tokens <= 0:
            raise UnsafeConfigurationError("model_max_output_tokens must be positive")

        if self.max_items_per_source <= 0:
            raise UnsafeConfigurationError("max_items_per_source must be positive")

        if self.max_input_bytes <= 0:
            raise UnsafeConfigurationError("max_input_bytes must be positive")

        _validate_allowed_repositories(self.allowed_repositories)

    def redacted_dict(self) -> dict[str, object]:
        """Serializable view. Secrets are reported as presence flags only."""

        return {
            "host": self.host,
            "port": self.port,
            "localhost_only": self.is_localhost_only,
            "allow_public_bind": self.allow_public_bind,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            # The path itself is deployment topology; report only whether
            # semantic retrieval is configured at all.
            "embedding_configured": bool(self.embedding_model_path),
            "ingest_interval_seconds": self.ingest_interval_seconds,
            "model_backend": self.model_backend,
            "model_name": self.model_name,
            "allowed_repositories": list(self.allowed_repositories),
            "max_input_bytes": self.max_input_bytes,
            "quarantine_prompt_injection": self.quarantine_prompt_injection,
            "api_token_configured": bool(self.api_token),
            "github_token_configured": bool(self.github_token),
            "ca_bundle_configured": bool(self.ca_bundle),
        }


_CACHED: Settings | None = None


def get_settings() -> Settings:
    """Return process-wide settings, loading from the environment once."""

    global _CACHED
    if _CACHED is None:
        _CACHED = Settings.from_env()
    return _CACHED


def reset_settings_cache() -> None:
    """Drop the cache. Used by tests that manipulate the environment."""

    global _CACHED
    _CACHED = None
