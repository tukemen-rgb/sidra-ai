"""Environment-driven settings.

Design rules for v0.1:

* Nothing here holds a secret value in source. Tokens are read from the
  environment at call time and never logged or serialized.
* The API binds to localhost. Exposing it beyond loopback requires an
  explicit opt-in *and* an API token, enforced in :meth:`Settings.validate`.
* The default model backend is local and needs no paid API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

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

#: Backends that run locally and cost nothing per token.
LOCAL_MODEL_BACKENDS: frozenset[str] = frozenset(
    {"echo", "ollama", "llama_cpp", "transformers"}
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


class UnsafeConfigurationError(RuntimeError):
    """Raised when a configuration would weaken a v0.1 safety invariant."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise UnsafeConfigurationError(f"{name} must be an integer") from exc


def _env_list(name: str, default: Iterable[str]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return tuple(default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    # --- API surface -----------------------------------------------------
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allow_public_bind: bool = False
    """Must be explicitly enabled *and* paired with an API token."""

    rate_limit_per_minute: int = 60

    # --- Model backend ---------------------------------------------------
    model_backend: str = "echo"
    model_name: str = "sidra-local-v0"
    model_endpoint: str = ""
    """Base URL for Ollama / llama.cpp server backends. Local by default."""

    model_max_output_tokens: int = 512

    # --- GitHub ingestion (read-only) ------------------------------------
    github_api_base: str = "https://api.github.com"
    allowed_repositories: tuple[str, ...] = DEFAULT_ALLOWED_REPOSITORIES
    github_request_timeout: float = 20.0
    max_items_per_source: int = 50

    # --- Security gate ---------------------------------------------------
    max_input_bytes: int = 512 * 1024
    quarantine_prompt_injection: bool = True

    # --- Storage ---------------------------------------------------------
    data_dir: str = field(default=".sidra")

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            host=os.environ.get("SIDRA_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST,
            port=_env_int("SIDRA_PORT", DEFAULT_PORT),
            allow_public_bind=_env_bool("SIDRA_ALLOW_PUBLIC_BIND", False),
            rate_limit_per_minute=_env_int("SIDRA_RATE_LIMIT_PER_MINUTE", 60),
            model_backend=os.environ.get("SIDRA_MODEL_BACKEND", "echo").strip()
            or "echo",
            model_name=os.environ.get("SIDRA_MODEL_NAME", "sidra-local-v0"),
            model_endpoint=os.environ.get("SIDRA_MODEL_ENDPOINT", ""),
            model_max_output_tokens=_env_int("SIDRA_MODEL_MAX_OUTPUT_TOKENS", 512),
            github_api_base=os.environ.get(
                "SIDRA_GITHUB_API_BASE", "https://api.github.com"
            ),
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

    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Enforce the v0.1 safety invariants."""

        if self.port < 1 or self.port > 65535:
            raise UnsafeConfigurationError("port out of range")

        if not self.is_localhost_only:
            if not self.allow_public_bind:
                raise UnsafeConfigurationError(
                    f"refusing to bind non-loopback host {self.host!r}: set "
                    "SIDRA_ALLOW_PUBLIC_BIND=true only after authentication and "
                    "rate limiting are reviewed"
                )
            if not self.api_token:
                raise UnsafeConfigurationError(
                    "non-loopback bind requires SIDRA_API_TOKEN to be set"
                )

        if self.model_backend not in LOCAL_MODEL_BACKENDS:
            raise UnsafeConfigurationError(
                f"model backend {self.model_backend!r} is not a local backend; "
                f"v0.1 allows {sorted(LOCAL_MODEL_BACKENDS)}"
            )

        if self.max_input_bytes <= 0:
            raise UnsafeConfigurationError("max_input_bytes must be positive")

        for repository in self.allowed_repositories:
            if "/" not in repository:
                raise UnsafeConfigurationError(
                    f"allowed repository {repository!r} must be 'owner/name'"
                )

    def redacted_dict(self) -> dict[str, object]:
        """Serializable view. Secrets are reported as presence flags only."""

        return {
            "host": self.host,
            "port": self.port,
            "localhost_only": self.is_localhost_only,
            "allow_public_bind": self.allow_public_bind,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "model_backend": self.model_backend,
            "model_name": self.model_name,
            "allowed_repositories": list(self.allowed_repositories),
            "max_input_bytes": self.max_input_bytes,
            "quarantine_prompt_injection": self.quarantine_prompt_injection,
            "api_token_configured": bool(self.api_token),
            "github_token_configured": bool(self.github_token),
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
