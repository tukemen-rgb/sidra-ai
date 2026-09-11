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
        # --check is the pre-flight an operator runs to confirm their posture, so
        # it must surface the same staged-model/echo caution the banner does -
        # otherwise the one known silent failure (a reviewed model staged but the
        # process running echo) passes the check without a word (C-1664). A
        # warning is not a refusal, so the check still succeeds (exit 0).
        warning = staged_model_but_running_echo(settings)
        if warning:
            print(warning)
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
        # Rate limiting keys requests by the ASGI client address. Uvicorn
        # enables proxy-header rewriting by default and can also read trusted
        # proxy ranges from FORWARDED_ALLOW_IPS, which would let local/process
        # environment state redefine that identity boundary. SIDRA v0.1 has no
        # reviewed reverse-proxy trust configuration, so preserve the actual
        # TCP peer address and ignore X-Forwarded-For/X-Forwarded-Proto.
        proxy_headers=False,
    )
    return 0


def staged_model_but_running_echo(settings: Settings) -> str:
    """A warning for the one silent failure this startup has, or "".

    ``echo`` is a supported backend and the clean-machine default, so warning
    on every echo start would be noise nobody reads. What is not normal is
    ``echo`` on a machine where somebody has already staged a real model: the
    reviewed manifest is written by ``scripts/setup_real_model.py`` and only
    exists because an operator ran it here.

    That combination has a known cause. On Windows the environment is set per
    terminal, so starting the server from a *new* window loses
    ``SIDRA_MODEL_BACKEND`` and the process falls back to ``echo`` - and
    everything then works, quietly, answering with an echo backend. The owner
    lost time to exactly this on 2026-09-02: the banner said
    ``model backend : echo`` and there was nothing to say that was unintended.

    Deliberately a warning and not a refusal. Running echo on a machine that
    also has a real model staged is a legitimate thing to want - it is how the
    offline suite and a clean-machine check are run - so this says what it
    sees and gets out of the way.
    """

    if settings.model_backend != "echo":
        return ""
    from pathlib import Path

    from sidra_ai.api.model_admission import MODEL_MANIFEST_FILENAME

    try:
        staged = (Path(settings.data_dir) / MODEL_MANIFEST_FILENAME).is_file()
    except OSError:  # an unreadable data dir is not this function's problem
        return ""
    if not staged:
        return ""
    return (
        "  注意          : この機械には審査済みモデルの manifest があるのに、"
        "今回は echo で起動しています。\n"
        "                  意図した通りならこのままで構いません。実モデルの"
        "つもりなら、環境変数はウィンドウごとに\n"
        "                  別なので、SIDRA_MODEL_BACKEND を"
        "「このウィンドウで」設定し直してから起動してください。"
    )


def _print_banner(settings: Settings) -> None:
    scope = "loopback only" if settings.is_localhost_only else "EXPOSED BEYOND LOOPBACK"
    # Bracket an IPv6 host (::1, an accepted loopback host) so the address a user
    # copies from this line is a valid URL - http://[::1]:8000, not the
    # unparseable http://::1:8000. Mirrors ask_cli.base_url (C-1679).
    host = f"[{settings.host}]" if ":" in settings.host else settings.host
    print(f"SIDRA AI  http://{host}:{settings.port}  ({scope})")
    print(f"  model backend : {settings.model_backend} ({settings.model_name})")
    print(f"  repositories  : {len(settings.allowed_repositories)} allowlisted")
    print("  github access : read-only")
    print(f"  auth token    : {'configured' if settings.api_token else 'not set'}")
    warning = staged_model_but_running_echo(settings)
    if warning:
        print(warning)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
