"""Does the CLI name a fetch route for a creation's companion flat artifacts too?

C-1715. C-1705 taught ``sidra-ask`` to print the ``/v1/artifacts/<name>`` route for
the primary ``artifact_path``, so a ``--url`` reader on another machine can retrieve
it. But a multi-file creation writes companions - a 3D model's ``.obj``/``.mtl``, a
deck's ``.pptx`` - as sibling flat artifacts in the same ``artifacts/`` directory,
retrievable at the same route. C-1275 made the CLI print their paths, but only the
paths: the route was still named for the preview alone. So a ``--url`` reader is
told 「.obj は … で開けます」 and 「.obj と一緒に置いてください」 and handed only the
server-side path of the ``.obj`` (the actual model) with no way to fetch it - the
exact asymmetry C-1705 closed for the preview. ``render`` now names the route for
each companion that is a flat artifact too.

The checks drive ``render`` with a 3D-model payload: each companion flat artifact
gets its ``/v1/artifacts/<name>`` route, the preview keeps its route, no route is
emitted without a base URL, a companion under ``projects/<slug>/`` gets no (wrong)
route, and the companion paths are still printed.
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


def _model_payload(artifact_path: str, details: dict) -> dict:
    return {
        "answer": ".obj は 3D ビューアーで開けます。色は .mtl から付くので一緒に置いてください。",
        "refused": False,
        "creation": {
            "intent": {"is_creation": True, "kind": "model3d"},
            "outcome": {
                "kind": "model3d", "handled": True, "summary": "s",
                "artifact_path": artifact_path, "details": details,
            },
        },
        "citations": [],
        "model": {"backend": "echo", "name": "x"},
    }


@dataclass(frozen=True)
class CliCompanionRouteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_names_companion_fetch_routes() -> CliCompanionRouteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    base = "http://192.168.1.9:8787"
    d = "/srv/data/.sidra/artifacts"
    preview = f"{d}/model3d-fish-20260912-preview.html"
    obj = f"{d}/model3d-fish-20260912.obj"
    mtl = f"{d}/model3d-fish-20260912.mtl"
    details = {"obj_path": obj, "mtl_path": mtl, "shape": "fish"}

    out = _render(_model_payload(preview, details), base_url=base)

    # --- (A) the .obj companion gets its retrieval route ---
    add(f"{base}/v1/artifacts/model3d-fish-20260912.obj" in out,
        f"A: no fetch route for the .obj companion: {out!r}")

    # --- (B) the .mtl companion gets its retrieval route ---
    add(f"{base}/v1/artifacts/model3d-fish-20260912.mtl" in out,
        f"B: no fetch route for the .mtl companion: {out!r}")

    # --- (C) the primary preview keeps its route (no regression of C-1705) ---
    add(f"{base}/v1/artifacts/model3d-fish-20260912-preview.html" in out,
        f"C: the primary artifact route regressed: {out!r}")

    # --- (D) without a base URL, no route is emitted (backward compatible) ---
    out_nobase = _render(_model_payload(preview, details))
    add("/v1/artifacts/" not in out_nobase,
        f"D: a route was emitted without a base URL: {out_nobase!r}")

    # --- (E) a companion under projects/<slug>/ gets no (wrong) route ---
    proj_obj = f"{d}/projects/deck-abc/model.obj"
    out_proj = _render(
        _model_payload(f"{d}/projects/deck-abc/deck.html", {"obj_path": proj_obj}),
        base_url=base,
    )
    add("/v1/artifacts/" not in out_proj,
        f"E: a wrong /v1/artifacts/ route was emitted for a project companion: {out_proj!r}")

    # --- (F) the companion paths themselves are still printed (C-1275 kept) ---
    add(obj in out and mtl in out,
        f"F: a companion path stopped being printed: {out!r}")

    total = 6
    return CliCompanionRouteResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliCompanionRouteResult", "evaluate_cli_names_companion_fetch_routes"]
