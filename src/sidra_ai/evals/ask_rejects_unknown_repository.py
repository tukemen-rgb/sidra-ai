"""Does ``sidra-ask`` catch a non-allowlisted ``--repository`` before sending?

C-1669. Scoping a query to a repository that is misspelt or not on the
allowlist makes ``sidra-api`` return ``403 "repository is not allowlisted"``.
The CLI rendered every 403 as "アクセスが拒否された。トークンと権限を確認する"
(access denied; check your token and permissions) - sending the reader to fix
authentication when the real problem is the repository name. The CLI already
holds the allowlist (``settings.allowed_repositories``), so - like the --top-k
range check - it now validates ``--repository`` before the request is built and
refuses with exit 2, naming the knob and the repositories that are allowed.

The checks drive ``main`` with a mock client: a non-allowlisted repo (must be
refused client-side, request never sent, guidance names --repository not the
token), an allowlisted repo (must pass through to the request), and a genuine
403 with no repository scope (the real auth path, unchanged).
"""

from __future__ import annotations

import contextlib
import io
import os
from dataclasses import dataclass

import httpx

_ALLOWED = "acme/docs,acme/wiki"


def _run(argv: list[str], *, status: int = 200):
    """Run main() with a mock client; return (exit, stderr, sent_flag)."""
    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import reset_settings_cache

    saved = {k: v for k, v in os.environ.items() if k.startswith("SIDRA_")}
    for k in list(os.environ):
        if k.startswith("SIDRA_"):
            del os.environ[k]
    os.environ["SIDRA_ALLOWED_REPOSITORIES"] = _ALLOWED

    sent = {"hit": False}

    def handler(request):
        sent["hit"] = True
        if status == 200:
            return httpx.Response(
                200,
                json={
                    "answer": "月曜が定休です。[S1]",
                    "refused": False,
                    "citations": [],
                    "model": {"backend": "ollama"},
                    "creation": {"intent": "qa"},
                },
            )
        return httpx.Response(status, json={"detail": "repository is not allowlisted"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    err = io.StringIO()
    try:
        reset_settings_cache()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = ask_cli.main(argv, client=client)
        return code, err.getvalue(), sent["hit"]
    finally:
        client.close()
        for k in list(os.environ):
            if k.startswith("SIDRA_"):
                del os.environ[k]
        os.environ.update(saved)
        reset_settings_cache()


@dataclass(frozen=True)
class AskRepoResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ask_rejects_unknown_repository() -> AskRepoResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) a non-allowlisted repository is caught before the request ---
    # status=403 is what the server would answer; the fix must refuse before the
    # request is ever sent, so the reader never sees the auth-token misdirection.
    code, err, sent = _run(["会社の休みは？", "--repository", "acme/typo"], status=403)
    add(code == 2, f"A: exit {code}, expected 2 (bad usage, caught client-side)")
    add("--repository" in err,
        f"A: the guidance did not name --repository: {err!r}")
    add("トークン" not in err,
        f"A: the guidance still sent the reader to the token: {err!r}")
    add(not sent, "A: the request was sent instead of being refused client-side")

    # --- (B) an allowlisted repository passes through to the request ---
    code, err, sent = _run(["会社の休みは？", "--repository", "acme/docs"])
    add(sent, f"B: an allowlisted repository was refused client-side: {err!r}")

    # --- (C) a real 403 with no repository scope keeps the auth guidance ---
    code, err, sent = _run(["会社の休みは？"], status=403)
    add(code == 1 and "トークン" in err,
        f"C: the genuine-auth 403 path changed: exit {code}, {err!r}")

    total = 6
    return AskRepoResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["AskRepoResult", "evaluate_ask_rejects_unknown_repository"]
