"""Does the CLI name a fetch route for a project creation's files too?

C-1730. C-1705/1715 taught ``sidra-ask`` to print the ``/v1/artifacts/<name>`` route
for a flat artifact and its companions, so a ``--url`` reader on another machine can
retrieve them - but deferred a *project* creation (a whole production) as "safe
side". A project's ``artifact_path`` is a directory under ``projects/<slug>/`` and
its files are served at ``/v1/projects/<slug>/<name>`` (the web UI's loadProjects
offers exactly those downloads). The CLI printed only the server-side directory
path, so a --url reader was handed a directory they cannot open and no way to fetch
any file of the production. ``render`` now names the ``/v1/projects/<slug>/<name>``
route for each file the outcome lists (skipping directory entries).

The checks drive ``render`` with a project payload: each file gets its project
route, a directory entry gets none, no route is emitted without a base URL, the
directory path line is kept, and a flat artifact / plain answer never gets a
``/v1/projects/`` route.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


def _render(payload: dict, base_url: str | None = None) -> str:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if base_url is None:
            render(payload)
        else:
            render(payload, base_url=base_url)
    return buf.getvalue()


_SLUG = "project-abc-20260912T000000Z"
_FILES = ["scenario.md", "structure.md", "assets/", "game.html", "production-log.md"]


def _project_payload() -> dict:
    return {
        "answer": "制作一式を作りました。",
        "refused": False,
        "creation": {
            "intent": {"is_creation": True, "kind": "project"},
            "outcome": {
                "kind": "project", "handled": True, "summary": "s",
                "artifact_path": f"/srv/data/.sidra/artifacts/projects/{_SLUG}",
                "details": {"slug": _SLUG, "files": _FILES, "stages": [],
                            "missing": [], "whole_project": True},
            },
        },
        "citations": [], "model": {"backend": "echo", "name": "x"},
    }


def _flat_payload() -> dict:
    return {
        "answer": "作りました。",
        "refused": False,
        "creation": {
            "intent": {"is_creation": True, "kind": "game"},
            "outcome": {
                "kind": "game", "handled": True, "summary": "s",
                "artifact_path": "/srv/data/.sidra/artifacts/game-shooter-20260912.html",
                "details": {},
            },
        },
        "citations": [], "model": {"backend": "echo", "name": "x"},
    }


def _qa_payload() -> dict:
    return {
        "answer": "本社の定休日は月曜です。", "refused": False,
        "creation": {"intent": {"is_creation": False, "kind": "unknown"}},
        "citations": [], "model": {"backend": "echo", "name": "x"},
    }


@dataclass(frozen=True)
class CliProjectRouteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_names_project_fetch_routes() -> CliProjectRouteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    base = "http://192.168.1.9:8787"
    out = _render(_project_payload(), base_url=base)

    # --- (A) a project file gets its /v1/projects/<slug>/<name> route ---
    add(f"{base}/v1/projects/{_SLUG}/game.html" in out,
        f"A: no project fetch route for game.html: {out!r}")

    # --- (B) a second file gets its route too ---
    add(f"{base}/v1/projects/{_SLUG}/production-log.md" in out,
        f"B: no project fetch route for production-log.md: {out!r}")

    # --- (C) a directory entry ('assets/') gets no route ---
    add(f"/v1/projects/{_SLUG}/assets/" not in out,
        f"C: a directory entry was given a route: {out!r}")

    # --- (D) without a base URL, no project route (backward compatible) ---
    out_nobase = _render(_project_payload())
    add("/v1/projects/" not in out_nobase,
        f"D: a project route was emitted without a base URL: {out_nobase!r}")

    # --- (E) the directory path line is still shown (no regression) ---
    add(f"projects/{_SLUG}" in out, f"E: the project path line regressed: {out!r}")

    # --- (F) a flat artifact / plain answer never gets a /v1/projects/ route ---
    flat = _render(_flat_payload(), base_url=base)
    qa = _render(_qa_payload(), base_url=base)
    add("/v1/projects/" not in flat and "/v1/projects/" not in qa,
        f"F: a /v1/projects/ route leaked to a flat/plain answer: flat={flat!r} qa={qa!r}")

    total = 6
    return CliProjectRouteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliProjectRouteResult", "evaluate_cli_names_project_fetch_routes"]
