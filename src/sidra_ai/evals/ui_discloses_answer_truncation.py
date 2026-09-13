"""Does the web UI say when a model answer was cut off at the token cap?

C-1753. C-1750 taught the backend to carry the stop reason and the CLI to say
"the answer is cut off" when a local model hit its output-token cap (Ollama
done_reason "length", llama.cpp stop_type "limit"), and put ``finish_reason`` in
the ``/v1/chat`` model block. Its sibling, the web UI's ``render()``, was left
behind (C-1750 deferred it): it drew the answer text and never read the model
block, so a browser reader - the surface most people use - saw a truncated answer
with no sign it was incomplete. ``render()`` now sets a truncation notice on the
status region (aria-live, so it is announced) when ``finish_reason`` is
``length``/``limit``; a normal ``stop`` and the echo backend add nothing.

The checks read the entry-page source (render reads model.finish_reason, checks
the two truncation codes, shows a guarded notice on the status line, no innerHTML)
and drive the real ``/v1/chat`` with a truncating model (the reason is carried).
"""

from __future__ import annotations

from sidra_ai.evals.scratch import scratch_dir

import re
from dataclasses import dataclass


def _ask_page() -> str:
    from sidra_ai.api.ui import ASK_PAGE

    return ASK_PAGE


def _chat_model_block(finish_reason: str) -> dict:
    from fastapi.testclient import TestClient

    from sidra_ai.api.app import create_app
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.base import GenerationResult
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    class _TruncatingModel(EchoModelAdapter):
        def generate(self, request):
            return GenerationResult(
                text="途中までの回答", backend="ollama", model="test-model",
                finish_reason=finish_reason,
            )

    gate = SecurityGate(GatePolicy(), allowed_repositories=())
    settings = Settings(data_dir=scratch_dir())
    service = SidraService(settings, model=_TruncatingModel(), store=DocumentStore(gate), gate=gate)
    client = TestClient(create_app(service=service, settings=settings))
    return client.post("/v1/chat", json={"message": "SIDRA とは？"}).json().get("model", {})


@dataclass(frozen=True)
class UiTruncationResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_ui_discloses_answer_truncation() -> UiTruncationResult:
    page = _ask_page()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) render() reads finish_reason from the response model block ---
    add(re.search(r"result\.model", page) is not None and "finish_reason" in page,
        "A: render() does not read model.finish_reason")

    # --- (B) both truncation codes are recognised (length and limit) ---
    add('"length"' in page and '"limit"' in page,
        "B: render() does not check for the length/limit stop reasons")

    # --- (C) a truncation notice wording is present ---
    add("出力上限" in page, "C: render() shows no truncation notice wording")

    # --- (D) the notice is guarded on a real finish_reason comparison, not
    #         shown for every answer ---
    add(re.search(r'finish_reason\s*===?\s*"length"', page) is not None,
        "D: the truncation notice is not guarded on finish_reason")

    # --- (E) nothing is rendered as markup (DATA stays text) ---
    add("innerHTML" not in page,
        "E: the page introduced innerHTML")

    # --- (F) the real /v1/chat carries the reason, so the UI has it to show ---
    block = _chat_model_block("length")
    add(block.get("finish_reason") == "length",
        f"F: /v1/chat did not carry finish_reason to the UI: {block!r}")

    total = 6
    return UiTruncationResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["UiTruncationResult", "evaluate_ui_discloses_answer_truncation"]
