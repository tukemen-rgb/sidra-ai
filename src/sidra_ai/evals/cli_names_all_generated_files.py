"""Does the CLI name every file a multi-file creation wrote?

C-1275: ``sidra-ask`` prints 「生成ファイル: <path>」 for a creation (C-1262), but
only ``artifact_path`` - the preview. A 3D model's summary says 「.obj は … 開けます」
yet the .obj and .mtl paths live in ``details`` and the terminal reader never saw
them; a deck's .pptx path is hidden the same way. So the summary points at a file
whose path the CLI never printed - C-1262 again, for the other files.

The render now also prints every other ``*_path`` detail that was written. A
single-file creation (art) is unchanged, and a non-path detail is never printed
as a file.

Measured by capturing the real ``render`` output, not a re-implementation.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass


def _render(payload: dict) -> str:
    from sidra_ai.api.ask_cli import render

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        render(payload)
    return buffer.getvalue()


def _creation(artifact_path: str, details: dict) -> dict:
    return {
        "answer": "作りました。",
        "citations": [],
        "creation": {"outcome": {"artifact_path": artifact_path, "details": details}},
    }


@dataclass(frozen=True)
class CliNamesFilesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_names_all_generated_files() -> CliNamesFilesResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # 3D model: preview is the artifact, .obj/.mtl are the files the summary
    # tells the reader to open.
    three_d = _render(_creation(
        "arts/model-preview.html",
        {"obj_path": "arts/model.obj", "mtl_path": "arts/model.mtl", "shape": "fish"},
    ))
    add("arts/model.obj" in three_d, f"3D: .obj path not shown in 「{three_d!r}」")
    add("arts/model.mtl" in three_d, f"3D: .mtl path not shown in 「{three_d!r}」")

    # Deck with a written .pptx: its path must be shown.
    deck_pptx = _render(_creation(
        "arts/deck.html", {"pptx_path": "arts/deck.pptx"},
    ))
    add("arts/deck.pptx" in deck_pptx, f"deck: .pptx path not shown in 「{deck_pptx!r}」")

    # Deck without a .pptx (empty path): nothing extra is printed.
    deck_nopptx = _render(_creation(
        "arts/deck.html", {"pptx_path": ""},
    ))
    add(".pptx" not in deck_nopptx, f"deck: empty .pptx path leaked in 「{deck_nopptx!r}」")

    # Single-file art with a non-path detail: the detail is not printed as a
    # file, and the one artifact is still shown.
    art = _render(_creation(
        "arts/art.html", {"pattern": "flowfield", "seed": 7},
    ))
    add("arts/art.html" in art and "flowfield" not in art,
        f"art: single-file render changed or leaked a non-path detail 「{art!r}」")

    total = 5
    return CliNamesFilesResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliNamesFilesResult", "evaluate_cli_names_all_generated_files"]
