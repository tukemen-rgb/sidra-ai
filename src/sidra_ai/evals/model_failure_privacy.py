"""Offline release-gate regression for local model failure privacy.

A local backend failure can carry endpoint, model, HTTP, or runtime diagnostics.
Those details are useful inside the process but must not cross the private API
response boundary.  This suite exercises the real ``SidraService`` and FastAPI
chat route with a dependency-free model stub; it opens no socket and performs
no external network call.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from sidra_ai.api.app import create_app
from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    ModelUnavailableError,
)


_PRIVATE_ENDPOINT = "http://127.0.0.1:11434"
_PRIVATE_MODEL = "sidra-private-model:7b"
_PRIVATE_MARKER = "private-local-runtime-detail"
_EXPECTED_REASON = "model backend unavailable"


class _UnavailableModel(LocalModelAdapter):
    """Local model stub whose failure text contains private runtime details."""

    backend = "echo"

    def __init__(self) -> None:
        super().__init__(_PRIVATE_MODEL)
        self.calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        raise ModelUnavailableError(
            f"ollama backend at {_PRIVATE_ENDPOINT} for {_PRIVATE_MODEL} failed: "
            f"{_PRIVATE_MARKER}"
        )


def run_model_failure_privacy_suite() -> tuple[EvalOutcome, ...]:
    """Require model-unavailable diagnostics to stay inside the process."""

    failures: list[str] = []

    with TemporaryDirectory(prefix="sidra-evals-") as data_dir:
        settings = Settings(data_dir=data_dir)
        model = _UnavailableModel()
        service = SidraService(settings=settings, model=model)
        response = TestClient(create_app(service, settings)).post(
            "/v1/chat",
            json={"message": "Summarize the indexed evidence."},
        )

        if model.calls != 1:
            failures.append(f"expected one model call, got {model.calls}")
        if response.status_code != 200:
            failures.append(f"expected HTTP 200 refusal, got {response.status_code}")
        else:
            body = response.json()
            if body.get("refused") is not True:
                failures.append("model failure did not produce a refusal")
            if body.get("answer") != "":
                failures.append("model failure returned a non-empty answer")
            if body.get("reason") != _EXPECTED_REASON:
                failures.append(
                    "model failure reason was not the constant redacted message"
                )

        serialized = response.text
        for private_value in (_PRIVATE_ENDPOINT, _PRIVATE_MODEL, _PRIVATE_MARKER):
            if private_value in serialized:
                failures.append("private model diagnostic survived in HTTP response")

    return (
        EvalOutcome(
            case_name="model_failure_diagnostics_private_at_api_boundary",
            passed=not failures,
            detail=(
                "local model failures must refuse with a constant reason and must not "
                "expose endpoint, model, or runtime diagnostics through /v1/chat"
            ),
            failures=tuple(failures),
        ),
    )
