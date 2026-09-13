"""Does a 200-status error body from the model server become a refusal, not empty?

C-1771. Ollama and llama.cpp can reply HTTP 200 with ``{"error": "..."}`` in the
body. The streaming methods guard against this (``generate_stream`` raises
``ModelUnavailableError`` on ``raw.get("error")``), but the non-streaming
``generate`` - the path every ``/v1/chat`` request takes - did not: it blindly
took ``raw.get("response"/"content", "")`` and returned an empty "successful"
answer, so ``service.chat`` never converted it to the ``model_unavailable``
refusal and the user saw a blank answer with none of the model-down guidance.

``generate`` now raises the same ``ModelUnavailableError`` its streaming twin
does. The checks drive the real adapters with an injected ``_post``/``_stream_lines``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


def _request():
    from sidra_ai.models.base import GenerationRequest

    return GenerationRequest(system_prompt="sys", user_message="q")


def _ollama(raw: dict, stream_lines=None):
    from sidra_ai.models.http_backends import OllamaAdapter

    class _Fake(OllamaAdapter):
        def __init__(self):
            super().__init__("m", endpoint="http://127.0.0.1:11434")

        def _post(self, path, payload):
            return raw

        def _stream_lines(self, path, payload):
            return iter(stream_lines or [])

    return _Fake()


def _llama(raw: dict):
    from sidra_ai.models.http_backends import LlamaCppAdapter

    class _Fake(LlamaCppAdapter):
        def __init__(self):
            super().__init__("m", endpoint="http://127.0.0.1:8080")

        def _post(self, path, payload):
            return raw

    return _Fake()


@dataclass(frozen=True)
class ModelErrorBodyResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_model_error_body_is_not_a_silent_empty_answer() -> ModelErrorBodyResult:
    from sidra_ai.models.base import ModelUnavailableError

    req = _request()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) Ollama generate raises on a 200 error body ------------------
    raised_a = None
    try:
        _ollama({"error": "model load failed"}).generate(req)
    except ModelUnavailableError as exc:
        raised_a = exc
    add(raised_a is not None,
        "A: Ollama generate returned a silent empty answer for a 200 error body")

    # --- (B) llama.cpp generate raises on a 200 error body --------------
    raised_b = None
    try:
        _llama({"error": "context overflow"}).generate(req)
    except ModelUnavailableError as exc:
        raised_b = exc
    add(raised_b is not None,
        "B: llama.cpp generate returned a silent empty answer for a 200 error body")

    # --- (C) a normal Ollama body still answers (no false positive) -----
    try:
        r_c = _ollama({"response": "hi"}).generate(req)
        ok_c = r_c.text == "hi"
    except Exception as exc:  # noqa: BLE001
        ok_c = False
    add(ok_c, "C: a normal Ollama response no longer produces its answer")

    # --- (D) a normal llama.cpp body still answers ----------------------
    try:
        r_d = _llama({"content": "hi"}).generate(req)
        ok_d = r_d.text == "hi"
    except Exception as exc:  # noqa: BLE001
        ok_d = False
    add(ok_d, "D: a normal llama.cpp response no longer produces its answer")

    # --- (E) the raised error is diagnosable (names the server's error) --
    add(raised_a is not None and "model load failed" in str(raised_a),
        f"E: the raised error does not carry the server's message: {raised_a!r}")

    # --- (F) the streaming twin still raises on a 200 error body --------
    #         (symmetry sentinel: the guard the non-streaming path now mirrors)
    stream_raised = None
    try:
        for _ in _ollama({}, stream_lines=[json.dumps({"error": "boom"})]).generate_stream(req):
            pass
    except ModelUnavailableError as exc:
        stream_raised = exc
    add(stream_raised is not None,
        "F: the streaming path no longer raises on a 200 error body")

    total = 6
    return ModelErrorBodyResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ModelErrorBodyResult",
    "evaluate_model_error_body_is_not_a_silent_empty_answer",
]
