"""Entry point. Refuses to start in an unsafe posture."""

from __future__ import annotations

import argparse
import sys

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings, UnsafeConfigurationError, get_settings
from sidra_ai.models.base import ModelUnavailableError
from sidra_ai.models.registry import BackendNotRegisteredError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sidra-api", description="Run the private SIDRA AI API (localhost by default)"
    )
    parser.add_argument("--host", default=None, help="override SIDRA_HOST")
    parser.add_argument("--port", type=int, default=None, help="override SIDRA_PORT")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate startup assembly without importing uvicorn or opening a socket",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = get_settings()
        if args.host is not None or args.port is not None:
            from dataclasses import replace

            settings = replace(
                settings,
                host=settings.host if args.host is None else args.host,
                port=settings.port if args.port is None else args.port,
            )
            settings.validate()
    except UnsafeConfigurationError as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2

    # Assemble both the service and FastAPI app before binding a listening
    # socket or printing the startup banner. Besides model/runtime admission,
    # this also exercises local audit-storage initialization in ``create_app``
    # so an unavailable or unsafe local path fails closed before the process
    # claims to have started.
    try:
        service = SidraService(settings=settings)
        api_app = create_app(service=service, settings=settings)
    except (BackendNotRegisteredError, ModelUnavailableError):
        print(
            "refusing to start: configured local model backend is unavailable or unsafe",
            file=sys.stderr,
        )
        return 2
    except OSError:
        # Storage constructors may fail on an unavailable, permission-denied,
        # or fail-closed local path. Refuse before socket bind, but never echo
        # the underlying filesystem path or OS diagnostic to the terminal.
        print(
            "refusing to start: local SIDRA storage is unavailable or unsafe",
            file=sys.stderr,
        )
        return 2

    if args.check:
        # The check path deliberately stops after the same service/app assembly
        # used by normal startup. This proves local model admission and storage
        # initialization without importing the ASGI server or opening a socket.
        print("SIDRA AI startup check passed; no socket opened")
        return 0

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required to serve the API: pip install uvicorn", file=sys.stderr)
        return 2

    _print_banner(settings)

    uvicorn.run(
        api_app,
        host=settings.host,
        port=settings.port,
    )
    return 0


def _print_banner(settings: Settings) -> None:
    scope = "loopback only" if settings.is_localhost_only else "EXPOSED BEYOND LOOPBACK"
    print(f"SIDRA AI  http://{settings.host}:{settings.port}  ({scope})")
    print(f"  model backend : {settings.model_backend} ({settings.model_name})")
    print(f"  repositories  : {len(settings.allowed_repositories)} allowlisted")
    print("  github access : read-only")
    print(f"  auth token    : {'configured' if settings.api_token else 'not set'}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
