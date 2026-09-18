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

from pathlib import Path

from dataclasses import dataclass, field
from typing import Callable, Protocol

from sidra_ai.creation.copy_writer import CopyWriter
from sidra_ai.creation.proposer import ParamProposer
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.records import append_standalone_record
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
    """Builds one kind of artifact from the operator's request.

    ``facts`` is the evidence the caller retrieved. It is passed to every
    generator rather than fetched by one, so a generator's output is bounded
    by exactly what it was handed - the property that makes "did this figure
    come from the corpus?" a question with an answer. An empty list is a
    supported input, not a degraded one.
    """

    def __call__(
        self,
        message: str,
        intent: CreationIntent,
        facts: list[Fact] | None = None,
    ) -> CreationOutcome: ...


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

    def __init__(self, record_dir: str | Path | None = None) -> None:
        self._generators: dict[CreationKind, CreationGenerator] = {}
        #: Where the record of each standalone creation is appended (C-1830).
        #: ``None`` keeps the old behaviour for callers that build a router
        #: without a data directory - a router that picked a directory of its
        #: own would write a log nobody knows about, the same reason the deck
        #: generator is left unregistered without one.
        self._record_dir = Path(record_dir) if record_dir else None

    def register(self, kind: CreationKind, generator: CreationGenerator) -> None:
        if kind is CreationKind.UNKNOWN:
            # There is no such thing as a generator for "something". Allowing
            # one would turn every unrecognised artifact into whatever that
            # generator happens to make.
            raise ValueError("cannot register a generator for CreationKind.UNKNOWN")
        self._generators[kind] = generator

    def registered_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(kind.value for kind in self._generators))

    def route(
        self,
        message: str,
        intent: CreationIntent,
        facts: list[Fact] | None = None,
    ) -> CreationOutcome:
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
        outcome = generator(message, intent, list(facts or []))
        self._record(outcome, facts, message)
        return outcome

    def _record(
        self, outcome: CreationOutcome, facts: list[Fact] | None, message: str = ""
    ) -> None:
        """Append one line saying what was just made, or do nothing.

        C-1830. ``records`` says it exists so that 「この game.html はいつ・何から
        作られたか」 has an answer a week later, and it was called from one
        place: the whole-production scaffold. The ordinary request - six
        generators, the common path - wrote nothing, so three games for 猫, 犬
        and 忍者 were three files named after the template they share.

        Here rather than in each generator because this is where all six meet;
        a record written six times is a record five of them can forget.

        Never raises into the answer. A log that cannot be written is worth a
        missing line, not a failed creation - the operator has the artifact.
        """

        if self._record_dir is None or not outcome.handled:
            return
        if not outcome.artifact_path:
            return
        details = dict(outcome.details)
        # C-1947: the record follows the language of the request, by the same
        # rule every other surface follows. The production log has done this
        # since C-1940; this is the common path - six generators - and it was
        # still writing Japanese to somebody who asked in English.
        # Imported here, not at module scope: `sidra_ai.creation.__init__`
        # imports this module and `models.echo` imports `creation.evidence`,
        # so a top-level import closes the circle and nothing loads at all.
        from sidra_ai.models.echo import _reply_in_japanese

        in_japanese = _reply_in_japanese(message)
        parameters: dict[str, object] = {"kind": outcome.kind.value}
        title = str(details.get("title") or "").strip()
        if title:
            parameters["題" if in_japanese else "title"] = title
        # The generator's own parameters, the same ones the production log
        # carries. Values that are lists or dicts say nothing to a reader here.
        for key in ("template", "difficulty", "pattern", "motif", "shape", "outline", "seed"):
            value = details.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                parameters[key] = value
        try:
            append_standalone_record(
                self._record_dir,
                made=[Path(outcome.artifact_path).name],
                # Source labels only. The text they pointed at never reaches a
                # file that reads as metadata (the module's own rule), and the
                # request itself is not written either: the audit log decided
                # it never holds request content.
                evidence=[fact.source for fact in (facts or []) if fact.source],
                parameters=parameters,
                in_japanese=in_japanese,
            )
        except OSError:
            return


def build_default_router(
    extra: dict[CreationKind, CreationGenerator] | None = None,
    *,
    data_dir: str | None = None,
    copy_writer: "CopyWriter | None" = None,
    param_proposer: "ParamProposer | None" = None,
) -> CreationRouter:
    """The router the API uses.

    ``data_dir`` is where generated artifacts are written. Without one the
    deck generator is left unregistered rather than defaulting to some path
    of its own choosing: a generator that writes files needs the caller to
    have decided where, and a router that silently picks a directory is how
    artifacts end up somewhere nobody looks.

    ``copy_writer`` is the optional model-backed naming provider. It is
    passed in rather than built here for the reason every other dependency
    is: a router that reached for the process's model would make "did a
    model touch this artifact?" unanswerable from the call site. Without
    one the generators are exactly what they were.

    ``extra`` is applied last, so a test can install its own generator over
    the default for a kind.
    """

    # C-1830: the record goes beside the artifacts, in the data directory
    # rather than inside artifacts/ - a file in there would be listed as
    # an artifact and change the total the listing reports.
    router = CreationRouter(record_dir=data_dir)
    if data_dir:
        # Imported here: the builders pull in HTML templates and the pptx
        # probe, and a module that only inspects the router should not pay
        # for them.
        from sidra_ai.creation.deck_job import build_deck_generator
        from sidra_ai.creation.game_job import build_game_generator
        from sidra_ai.creation.model3d_job import build_model3d_generator

        router.register(CreationKind.DECK, build_deck_generator(data_dir, None, copy_writer))
        router.register(
            CreationKind.GAME,
            build_game_generator(data_dir, copy_writer, param_proposer),
        )
        router.register(CreationKind.MODEL3D, build_model3d_generator(data_dir))

        from sidra_ai.creation.gif_job import build_gif_generator

        router.register(CreationKind.GIF, build_gif_generator(data_dir))

        from sidra_ai.creation.art_job import build_art_generator

        router.register(CreationKind.ART, build_art_generator(data_dir))

        from sidra_ai.creation.document_job import build_document_generator

        router.register(CreationKind.DOCUMENT, build_document_generator(data_dir))

        from sidra_ai.creation.project_job import build_project_generator

        router.register(CreationKind.PROJECT, build_project_generator(data_dir))
    for kind, generator in (extra or {}).items():
        router.register(kind, generator)
    return router


__all__ = [
    "CreationGenerator",
    "CreationOutcome",
    "CreationRouter",
    "build_default_router",
]
