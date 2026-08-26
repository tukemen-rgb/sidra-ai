"""Turning a request to *make* something into a routed creation job.

``/v1/chat`` answers questions. "釣りゲームを作って" is not a question, and
answering it with a paragraph about fishing games is the wrong shape of
output. This package decides which of the two a message is, and hands the
creation ones to a generator.

The decision is deterministic and conservative on purpose: an unrecognised
message stays a question, because the cost of misreading a question as a
creation request (a confused answer) is worse than the cost of missing a
creation request (an ordinary answer).
"""

from sidra_ai.creation.intent import (
    CreationIntent,
    CreationKind,
    detect_creation_intent,
)
from sidra_ai.creation.router import CreationRouter, CreationOutcome

__all__ = [
    "CreationIntent",
    "CreationKind",
    "CreationOutcome",
    "CreationRouter",
    "detect_creation_intent",
]
