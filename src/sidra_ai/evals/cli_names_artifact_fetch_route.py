"""Does the CLI name a retrieval route for a generated artifact?

C-1705. On a creation, ``sidra-ask`` printed only the artifact's server-side
filesystem path. That opens for a localhost user but not for one reaching a
server over ``--url`` - the path is on the server. The web UI, by contrast,
offers a download by name via ``/v1/artifacts/{name}``. ``render`` now also names
that retrieval route (for a flat artifact, whose route is unambiguous) when it
knows the base URL, closing the same client asymmetry as C-1675/1689/1691.

The checks drive ``render`` with a creation payload: the route appears with the
base URL and names the artifact's basename, is absent without a base URL (backward
compatible), is not emitted with a wrong ``/v1/artifacts/`` URL for a project-file
path, and never appears for a plain answer.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


def _render(payload: dict, base_url: str | None = None) -> str:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            if base_url is None:
                render(payload)
            else:
                render(payload, base_url=base_url)
        except TypeError:
            # Pre-fix signature has no base_url: fall back so the eval measures
            # "route absent" rather than crashing.
            render(payload)
    return buf.getvalue()


def _creation_payload(artifact_path: str) -> dict:
    return {
        "answer": "作りました。ブラウザで開けば遊べます。",
        "refused": False,
        "creation": {
            "intent": {"is_creation": True, "kind": "game"},
            "outcome": {
                "kind": "game", "handled": True, "summary": "s",
                "artifact_path": artifact_path, "details": {},
            },
        },
        "citations": [],
        "model": {"backend": "echo", "name": "x"},
    }


def _qa_payload() -> dict:
    return {
        "answer": "本社の定休日は月曜です。",
        "refused": False,
        "creation": {"intent": {"is_creation": False, "kind": "unknown"}},
        "citations": [],
        "model": {"backend": "echo", "name": "x"},
    }


@dataclass(frozen=True)
class CliFetchRouteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_names_artifact_fetch_route() -> CliFetchRouteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    base = "http://192.168.1.9:8787"
    flat_path = "/srv/data/.sidra/artifacts/game-shooter-20260912.html"
    name = "game-shooter-20260912.html"
    route = f"{base}/v1/artifacts/{name}"

    out = _render(_creation_payload(flat_path), base_url=base)

    # --- (A) the retrieval route is named for a flat artifact ---
    add(route in out, f"A: no fetch route for a flat artifact: {out[-120:]!r}")

    # --- (B) the route names the artifact's basename, not the full path ---
    add(f"/v1/artifacts/{name}" in out and f"/v1/artifacts/{flat_path}" not in out,
        "B: the fetch route did not use the artifact basename")

    # --- (C) without a base URL, no route is emitted (backward compatible) ---
    out_nobase = _render(_creation_payload(flat_path))
    add("/v1/artifacts/" not in out_nobase,
        f"C: a route was emitted without a base URL: {out_nobase[-100:]!r}")

    # --- (D) the generated-file path line is still shown (no regression) ---
    add(flat_path in out, "D: the generated-file path line regressed")

    # --- (E) a project-file path gets no (wrong) /v1/artifacts/ URL ---
    proj_path = "/srv/data/.sidra/artifacts/projects/deck-abc/deck.html"
    out_proj = _render(_creation_payload(proj_path), base_url=base)
    add("/v1/artifacts/" not in out_proj,
        f"E: a wrong /v1/artifacts/ URL was emitted for a project file: {out_proj[-120:]!r}")

    # --- (F) a plain (non-creation) answer names no artifact route ---
    out_qa = _render(_qa_payload(), base_url=base)
    add("/v1/artifacts/" not in out_qa,
        "F: a fetch route appeared for a non-creation answer")

    total = 6
    return CliFetchRouteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliFetchRouteResult", "evaluate_cli_names_artifact_fetch_route"]
