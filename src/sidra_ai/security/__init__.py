"""Security gate: all external content is DATA, never an instruction."""

from sidra_ai.security.data_envelope import (
    DATA_CONTRACT,
    InstructionAuthorityError,
    build_data_context,
    neutralize,
    wrap_block,
)
from sidra_ai.security.decisions import (
    Decision,
    Finding,
    FindingCategory,
    GateResult,
    Severity,
    strictest,
)
from sidra_ai.security.detectors import (
    OversizeDetector,
    PIIDetector,
    PromptInjectionDetector,
    SecretDetector,
    SourceAllowlistDetector,
    shannon_entropy,
)
from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate
from sidra_ai.security.redaction import placeholder, redact_spans

__all__ = [
    "DATA_CONTRACT",
    "Decision",
    "Finding",
    "FindingCategory",
    "GatePolicy",
    "GateResult",
    "InstructionAuthorityError",
    "OversizeDetector",
    "PIIDetector",
    "PromptInjectionDetector",
    "QuarantineStore",
    "SecretDetector",
    "SecurityGate",
    "Severity",
    "SourceAllowlistDetector",
    "build_data_context",
    "neutralize",
    "placeholder",
    "redact_spans",
    "shannon_entropy",
    "strictest",
    "wrap_block",
]
