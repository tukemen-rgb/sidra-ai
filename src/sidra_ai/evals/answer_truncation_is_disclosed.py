"""Is a model answer cut off at the token cap disclosed, not shown as complete?

C-1750. On the production path (ollama/llama_cpp), a request carries
``max_output_tokens`` = ``model_max_output_tokens`` (default 512). When the server
stops because it hit that cap, it says so - Ollama returns ``done_reason:
"length"``, llama.cpp ``stop_type: "limit"`` - and the *streaming* paths capture
it (``generate_stream`` sets ``finish_reason`` from those keys). But the
non-streaming ``_finish`` - the one ``/v1/chat`` actually uses - discarded it, so
``GenerationResult.finish_reason`` defaulted to ``"stop"``. A mid-sentence answer
was returned as complete, the chat ``model`` block carried no reason, and neither
client said a word: the reader got a truncated answer with no sign it was cut off,
in the one product built on "say when it is not the whole thing" (C-1680/C-1264).

``_finish`` now reads ``done_reason``/``stop_type`` like its streaming twin, the
chat ``model`` block carries ``finish_reason``, and the CLI prints a truncation
notice when it is ``length``/``limit`` (a normal ``stop`` and echo add nothing).

The checks call the real ``_finish`` (both backends, and the normal case), drive
``/v1/chat`` with a truncating model, and drive the CLI ``render``.
"""

from __future__ import annotations

from sidra_ai.evals.scratch import scratch_dir

import contextlib
import io
from dataclasses import dataclass

_TRUNCATED = ("length", "limit")


def _finish_reason(adapter_cls, raw: dict) -> str:
    from sidra_ai.models.base import GenerationRequest

    adapter = adapter_cls("test-model")
    req = GenerationRequest(system_prompt="s", user_message="u")
    return adapter._finish(req, "途中までの本文", raw).finish_reason


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
        """A local adapter whose answer was cut off at the token cap."""

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


def _render(payload: dict) -> str:
    from sidra_ai.api.ask_cli import render

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        render(payload)
    return buf.getvalue()


def _answer_payload(finish_reason: str) -> dict:
    return {
        "answer": "途中までの回答", "refused": False, "citations": [],
        "model": {"backend": "ollama", "name": "m", "finish_reason": finish_reason},
    }


@dataclass(frozen=True)
class AnswerTruncationResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_answer_truncation_is_disclosed() -> AnswerTruncationResult:
    from sidra_ai.models.http_backends import LlamaCppAdapter, OllamaAdapter

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) Ollama: a cap-stop (done_reason "length") is captured ---
    a = _finish_reason(OllamaAdapter, {"done_reason": "length", "eval_count": 512})
    add(a == "length", f"A: Ollama _finish dropped done_reason: {a!r}")

    # --- (B) llama.cpp: a cap-stop (stop_type "limit") is captured ---
    b = _finish_reason(LlamaCppAdapter, {"stop_type": "limit", "tokens_predicted": 512})
    add(b == "limit", f"B: llama.cpp _finish dropped stop_type: {b!r}")

    # --- (C) a normal completion stays "stop" (no false truncation) ---
    c = _finish_reason(OllamaAdapter, {"done_reason": "stop", "eval_count": 20})
    add(c == "stop", f"C: a normal completion was not 'stop': {c!r}")

    # --- (D) the /v1/chat model block carries the reason end-to-end ---
    block = _chat_model_block("length")
    add(block.get("finish_reason") == "length",
        f"D: /v1/chat model block dropped finish_reason: {block!r}")

    # --- (E) the CLI discloses a truncated answer ---
    out_e = _render(_answer_payload("length"))
    add("上限" in out_e and "途中" in out_e,
        f"E: the CLI did not disclose a truncated answer: {out_e!r}")

    # --- (F) a normal answer gets no truncation notice (no over-warning) ---
    out_f = _render(_answer_payload("stop"))
    add("上限" not in out_f,
        f"F: the CLI warned truncation on a complete answer: {out_f!r}")

    total = 6
    return AnswerTruncationResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["AnswerTruncationResult", "evaluate_answer_truncation_is_disclosed"]
