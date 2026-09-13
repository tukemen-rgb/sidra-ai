"""Does the web UI say when an answer has no indexed grounding?

C-1762. The CLI's ``_print_citations`` prints "引用なし。索引に根拠が無いか、取り込みがまだ走っていない。" for an
answered, non-refusal, non-creation turn that carries no citations - so a new user
who asks before ingesting learns the corpus is empty. The web UI's ``render()``
returned silently on no citations (``if (!citations.length) { return; }``), so a
browser reader saw a bare answer with no sign it was ungrounded - in a product
whose selling point is provenance. ``render()`` now shows the same note in the
sources region (text only), guarded like the CLI: not for refusals, not for
creations.

The checks read the entry-page source and drive the real ``/v1/chat`` on an empty
corpus so the ungrounded condition is genuine.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass

# The exact wording the CLI prints (ask_cli._print_citations); parity target.
_NOTE = "取り込みがまだ走っていない"


def _ask_page() -> str:
    from sidra_ai.api.ui import ASK_PAGE

    return ASK_PAGE


def _empty_corpus_chat() -> dict:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    settings = Settings(data_dir=tempfile.mkdtemp())
    service = SidraService(settings)  # echo backend, empty store
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": "SIDRA とは？"}).json()


@dataclass(frozen=True)
class MissingGroundingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_discloses_missing_grounding() -> MissingGroundingResult:
    page = _ask_page()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) the no-grounding note wording is present (CLI parity) ---------
    add(_NOTE in page, "A: render() shows no no-grounding note wording")

    # --- (B) the note is guarded so a refusal does not also get it --------
    add(re.search(r"!result\.refused\s*&&\s*!creationOutcome", page) is not None,
        "B: the no-grounding note is not guarded on !result.refused")

    # --- (C) creation turns are excluded (they never cite) ----------------
    add(re.search(r"result\.creation", page) is not None and "creationOutcome" in page,
        "C: the note does not exclude creation turns (creation outcome guard)")

    # --- (D) nothing is rendered as markup (DATA stays text) --------------
    add("innerHTML" not in page, "D: the page introduced innerHTML")

    # --- (E) the real /v1/chat on an empty corpus answers with no citations
    #         (so the condition the note discloses is genuine) -------------
    body = _empty_corpus_chat()
    add(body.get("citations") == [] and bool(body.get("answer"))
        and not body.get("refused"),
        f"E: /v1/chat did not produce an ungrounded answer: "
        f"citations={body.get('citations')!r} answer={bool(body.get('answer'))} "
        f"refused={body.get('refused')!r}")

    # --- (F) the note goes into the sources region (not the status line) --
    add(re.search(r"sources\.appendChild\(note\)", page) is not None,
        "F: the no-grounding note is not appended to the sources region")

    total = 6
    return MissingGroundingResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["MissingGroundingResult", "evaluate_ui_discloses_missing_grounding"]
