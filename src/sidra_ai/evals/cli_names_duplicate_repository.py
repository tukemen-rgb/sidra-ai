"""Does ``sidra-ask`` name a duplicate ``--repository`` instead of misdirecting?

C-1767. ``--repository`` may be repeated, and the allowlist check is
case-insensitive (settings.is_repository_allowed), so ``--repository X
--repository X`` (or ``X`` / ``x``) passes the CLI's client-side pre-check and is
sent. The server's ``_validate_repository_scope`` rejects case-insensitive
duplicates with 422, which the CLI renders as "your input is too long or
malformed; shorten it and resend" - editing the *question* can never fix a
duplicated flag, the same misdirection C-1661/C-1669 removed for other knobs. The
CLI now rejects a duplicate ``--repository`` itself, before sending, naming it.

The checks drive ``ask_cli.main`` with an injected client that records whether a
request was sent: a duplicate must fail as bad usage (exit 2) without sending
anything and name the repository; distinct values must pass through unchanged.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

REPO_A = "tukemen-rgb/Fg"
REPO_B = "tukemen-rgb/site"


class _RecordingClient:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.posts: list[dict] = []

    def post(self, url: str, json: dict):  # noqa: A002 - mirrors httpx signature
        self.posts.append(json)
        return _RecordingResponse()

    def close(self) -> None:  # pragma: no cover - injected clients are not owned
        pass


class _RecordingResponse:
    status_code = 200

    def json(self) -> dict:
        return {"answer": "ok", "citations": []}


def _run(argv: list[str]):
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import Settings

    settings = Settings(
        host="127.0.0.1", port=8000,
        allowed_repositories=(REPO_A, REPO_B),
    )
    original = ask_cli.get_settings
    ask_cli.get_settings = lambda: settings
    client = _RecordingClient()
    err = io.StringIO()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = ask_cli.main(argv, client=client)
    finally:
        ask_cli.get_settings = original
    return code, err.getvalue(), client


@dataclass(frozen=True)
class DuplicateRepoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_names_duplicate_repository() -> DuplicateRepoResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) an exact duplicate is bad usage (exit 2) --------------------
    code, err, client = _run(["q", "--repository", REPO_A, "--repository", REPO_A])
    add(code == 2, f"A: exact duplicate --repository exited {code}, expected 2")
    # --- (B) ...and nothing is sent (the 422 misdirection is never reached)
    add(not client.posts, "B: a request was sent for a duplicate --repository")
    # --- (F) ...and the message names the duplicated repository ----------
    add(REPO_A in err, f"F: the duplicate message does not name the repository: {err!r}")

    # --- (C) a case-variant duplicate is caught too (case-insensitive) ---
    code_c, err_c, client_c = _run(
        ["q", "--repository", REPO_A, "--repository", REPO_A.lower()]
    )
    add(code_c == 2 and not client_c.posts,
        f"C: case-variant duplicate not rejected before send: exit {code_c}, "
        f"posts={len(client_c.posts)}")

    # --- (D) distinct allowlisted repositories pass through unchanged ----
    code_d, _, client_d = _run(["q", "--repository", REPO_A, "--repository", REPO_B])
    add(code_d == 0 and len(client_d.posts) == 1
        and client_d.posts[0].get("repositories") == [REPO_A, REPO_B],
        f"D: distinct repositories did not pass through: exit {code_d}, "
        f"posts={client_d.posts!r}")

    # --- (E) a single --repository is unaffected ------------------------
    code_e, _, client_e = _run(["q", "--repository", REPO_A])
    add(code_e == 0 and len(client_e.posts) == 1,
        f"E: a single --repository was rejected: exit {code_e}, posts={len(client_e.posts)}")

    total = 6
    return DuplicateRepoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DuplicateRepoResult", "evaluate_cli_names_duplicate_repository"]
