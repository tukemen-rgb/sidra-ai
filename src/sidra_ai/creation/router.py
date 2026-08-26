"""Handing a recognised creation request to whatever can build it.

The router is deliberately thin and knows nothing about games or decks. It
holds generators registered by kind and reports honestly when none is
registered, which is the state this file ships in: the detector and the
route exist, the builders arrive with their own backlog items.

That honesty is the design. A router that silently fell back to answering
the question would make "was it routed?" unmeasurable from outside, and an
unmeasurable capability is one nobody can tell apart from an absent one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from sidra_ai.creation.intent import CreationIntent, CreationKind


@dataclass(frozen=True)
class CreationOutcome:
    """What happened to a routed request.

    ``artifact_path`` is a local path and nothing else - no URL, no content.
    Generated files stay on the operator's disk; this project has no route
    that sends one anywhere.
    """

    kind: CreationKind
    handled: bool
    summary: str
    artifact_path: str = ""
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "handled": self.handled,
            "summary": self.summary,
            "artifact_path": self.artifact_path,
            "details": dict(self.details),
        }


class CreationGenerator(Protocol):
    """Builds one kind of artifact from the operator's request."""

    def __call__(self, message: str, intent: CreationIntent) -> CreationOutcome: ...


#: What an operator sees when the route works but nothing can build the
#: thing yet. Phrased as a statement of fact rather than an apology, and it
#: names the kind, so the message distinguishes "SIDRA did not understand"
#: from "SIDRA understood and cannot build this".
_NO_GENERATOR = (
    "この依頼は制作リクエスト（{kind}）として認識しましたが、"
    "対応する生成器がまだ登録されていません。"
)


class CreationRouter:
    """Registry of generators, keyed by what they make.

    Registration is explicit rather than discovered by import scanning: a
    generator that appears because a module happened to be imported is a
    generator nobody decided to enable.
    """

    def __init__(self) -> None:
        self._generators: dict[CreationKind, CreationGenerator] = {}

    def register(self, kind: CreationKind, generator: CreationGenerator) -> None:
        if kind is CreationKind.UNKNOWN:
            # There is no such thing as a generator for "something". Allowing
            # one would turn every unrecognised artifact into whatever that
            # generator happens to make.
            raise ValueError("cannot register a generator for CreationKind.UNKNOWN")
        self._generators[kind] = generator

    def registered_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(kind.value for kind in self._generators))

    def route(self, message: str, intent: CreationIntent) -> CreationOutcome:
        """Run the generator for ``intent``, or report that there is none.

        The caller decides whether to route at all; by the time a message
        reaches here it has already been judged a creation request. This
        never raises for an unregistered kind, because a missing generator
        is a state to report, not an error to propagate into an HTTP 500.
        """

        generator = self._generators.get(intent.kind)
        if generator is None:
            return CreationOutcome(
                kind=intent.kind,
                handled=False,
                summary=_NO_GENERATOR.format(kind=intent.kind.value),
                details={"registered_kinds": list(self.registered_kinds())},
            )
        return generator(message, intent)


def build_default_router(
    extra: dict[CreationKind, CreationGenerator] | None = None,
) -> CreationRouter:
    """The router the API uses.

    Empty today. C-991 and C-992 register the game and deck generators here,
    and ``extra`` lets a test install a generator without reaching into the
    module's state.
    """

    router = CreationRouter()
    for kind, generator in (extra or {}).items():
        router.register(kind, generator)
    return router


__all__ = [
    "CreationGenerator",
    "CreationOutcome",
    "CreationRouter",
    "build_default_router",
]
