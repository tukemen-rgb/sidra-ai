"""Offline regressions for the operator/model security boundaries.

Input/RAG screening is not enough: a local model can echo or synthesize a
credential after retrieval. The API lane applies :class:`OutputGuard` before
returning model text, so the default ``sidra-evals`` suite protects both the
guard itself and its composition into :class:`SidraService`.

All cases are synthetic, deterministic, offline, and never contain a functional
credential.
"""

from __future__ import annotations

import base64
from tempfile import TemporaryDirectory
from urllib.parse import quote

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.cases import EvalOutcome
from sidra_ai.models.base import GenerationRequest, GenerationResult, LocalModelAdapter
from sidra_ai.security.output_guard import OutputGuard


def _fake_github_token() -> str:
    # Built at runtime so the eval source itself never embeds a complete
    # credential-shaped literal.
    return "ghp_" + "0" * 36


def _html_entity_github_token() -> str:
    """Synthetic provider-token shape with the underscore rendered as an entity."""

    return "ghp&#95;" + "0" * 36


def _high_entropy_secret() -> str:
    return "A1b2C3d4E5f6G7h8I9j0K_l-MnOpQrStUvWxYz1234567890"


def _safe_commit_sha() -> str:
    """Synthetic provenance identifier that must not be mistaken for PII."""

    return "0123456789abcdef" * 2 + "01234567"


class _FixedOutputModel(LocalModelAdapter):
    """Dependency-free model stub used to verify the service trust boundary."""

    backend = "echo"

    def __init__(self, text: str) -> None:
        super().__init__("sidra-eval-fixed-output")
        self._text = text
        self.calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        return GenerationResult(
            text=self._text,
            backend=self.backend,
            model=self.model,
        )


def _run_service_boundary_case(token: str) -> EvalOutcome:
    """Prove the L5 composition root applies L2 without destroying provenance.

    Direct ``OutputGuard`` tests can stay green even if a future API/service
    refactor forgets to call the guard. This case injects deterministic model
    results through ``SidraService.chat`` and fails if either a raw or reversibly
    encoded sensitive value reaches any returned field. A safe provenance-shaped
    result containing a commit SHA must pass through unchanged; otherwise
    security precision regressions can make grounded GitHub answers unusable
    even when the detector unit tests pass.
    """

    failures: list[str] = []
    safe_commit = _safe_commit_sha()
    safe_text = f"Verified checkpoint {safe_commit} from the indexed repository."

    with TemporaryDirectory(prefix="sidra-evals-") as data_dir:
        blocked_model = _FixedOutputModel(token)
        blocked_service = SidraService(
            settings=Settings(data_dir=data_dir),
            model=blocked_model,
        )
        blocked_response = blocked_service.chat("Summarize the indexed evidence.")

        if blocked_model.calls != 1:
            failures.append(
                f"service boundary: expected one model call, got {blocked_model.calls}"
            )
        if blocked_response.get("refused") is not True:
            failures.append("service boundary: sensitive model output was not refused")
        if token in repr(blocked_response):
            failures.append("service boundary: sensitive model output survived in response")

        entity_encoded = _html_entity_github_token()
        entity_model = _FixedOutputModel(entity_encoded)
        entity_service = SidraService(
            settings=Settings(data_dir=data_dir),
            model=entity_model,
        )
        entity_response = entity_service.chat("Summarize the indexed evidence.")

        if entity_model.calls != 1:
            failures.append(
                "service boundary: HTML-entity case expected one model call, "
                f"got {entity_model.calls}"
            )
        if entity_response.get("refused") is not True:
            failures.append("service boundary: HTML-entity encoded output was not refused")
        if entity_encoded in repr(entity_response):
            failures.append("service boundary: HTML-entity payload survived in response")
        if token in repr(entity_response):
            failures.append("service boundary: decoded credential survived in response")

        safe_model = _FixedOutputModel(safe_text)
        safe_service = SidraService(
            settings=Settings(data_dir=data_dir),
            model=safe_model,
        )
        safe_response = safe_service.chat("Summarize the indexed evidence.")

        if safe_model.calls != 1:
            failures.append(
                f"service boundary: safe case expected one model call, got {safe_model.calls}"
            )
        if safe_response.get("refused") is not False:
            failures.append("service boundary: safe provenance output was refused")
        if safe_response.get("answer") != safe_text:
            failures.append("service boundary: safe provenance output was mutated")
        if safe_commit not in str(safe_response.get("answer", "")):
            failures.append("service boundary: safe commit provenance was not preserved")

    return EvalOutcome(
        case_name="output_guard_service_boundary",
        passed=not failures,
        detail=(
            "SidraService.chat must withhold raw or reversibly encoded sensitive model "
            "output before returning any field while preserving safe commit provenance "
            "byte-for-byte"
        ),
        failures=tuple(failures),
    )


def _run_operator_input_boundary_case(token: str) -> EvalOutcome:
    """Prove sensitive operator input is refused before retrieval/model use.

    Detector unit tests can remain green while a future service refactor routes
    the original operator string around the gate, echoes it in a refusal payload,
    or invokes the model before returning the refusal. This case protects the
    composition boundary for both chat and model-free retrieval.
    """

    failures: list[str] = []
    prompt = "Please inspect this accidental credential: " + token

    with TemporaryDirectory(prefix="sidra-evals-") as data_dir:
        model = _FixedOutputModel("the model must not run for refused input")
        service = SidraService(
            settings=Settings(data_dir=data_dir),
            model=model,
        )

        chat_response = service.chat(prompt)
        if chat_response.get("refused") is not True:
            failures.append("operator boundary: secret-bearing chat input was not refused")
        if model.calls != 0:
            failures.append(
                f"operator boundary: refused chat input invoked model {model.calls} time(s)"
            )
        if token in repr(chat_response):
            failures.append("operator boundary: chat refusal echoed the credential")

        retrieve_response = service.retrieve(prompt)
        if retrieve_response.get("refused") is not True:
            failures.append("operator boundary: secret-bearing retrieve input was not refused")
        if model.calls != 0:
            failures.append("operator boundary: model-free retrieve path invoked the model")
        if token in repr(retrieve_response):
            failures.append("operator boundary: retrieve refusal echoed the credential")

    return EvalOutcome(
        case_name="operator_input_service_boundary",
        passed=not failures,
        detail=(
            "secret-bearing operator input must be refused before retrieval/model use "
            "and no response field may echo the original credential"
        ),
        failures=tuple(failures),
    )


def run_output_security_suite() -> tuple[EvalOutcome, ...]:
    """Require input/output security at detector and service-integration layers."""

    guard = OutputGuard()
    token = _fake_github_token()
    entity_token = _html_entity_github_token()
    personal_email = "kenji.tanaka@example.co.jp"

    blocked_cases = {
        "raw_provider_token": token,
        "unicode_fullwidth_token": "ｇｈｐ＿" + "０" * 36,
        "base64_token": base64.b64encode(token.encode("utf-8")).decode("ascii"),
        "percent_encoded_email": quote(personal_email, safe=""),
        "hex_token": token.encode("utf-8").hex(),
        "escaped_token": "".join(f"\\u{ord(char):04x}" for char in token),
        "html_entity_email": "kenji.tanaka&#64;example.co.jp",
        "html_entity_token": entity_token,
        "base64_html_entity_token": base64.b64encode(entity_token.encode("utf-8")).decode(
            "ascii"
        ),
        "unprefixed_high_entropy_secret": _high_entropy_secret(),
        "decoder_bound_exceeded": r"\u0061" * 4097,
    }
    allowed_cases = {
        "ordinary_output": "SIDRA AI uses a local model and cites retrieved evidence.",
        "role_email": "For service support, use support@example.com.",
        "commit_sha": "Checkpoint " + _safe_commit_sha() + ".",
        "benign_html_entities": "AT&amp;T documentation uses &copy; as a rendering example.",
    }

    failures: list[str] = []

    for name, content in blocked_cases.items():
        result = guard.scan(content)
        if not result.blocked:
            failures.append(f"{name}: reversible sensitive output was allowed")
            continue
        if content and content in result.content:
            failures.append(f"{name}: blocked response retained original sensitive payload")

    for name, content in allowed_cases.items():
        result = guard.scan(content)
        if result.blocked:
            failures.append(f"{name}: safe output was blocked")
        elif result.content != content:
            failures.append(f"{name}: safe output was mutated")

    guard_outcome = EvalOutcome(
        case_name="output_guard_reversible_exfiltration",
        passed=not failures,
        detail=(
            "raw/fullwidth/base64/percent/hex/escaped/HTML-entity/high-entropy output "
            "must fail closed while ordinary/provenance output remains byte-for-byte unchanged"
        ),
        failures=tuple(failures),
    )

    return (
        guard_outcome,
        _run_service_boundary_case(token),
        _run_operator_input_boundary_case(token),
    )
