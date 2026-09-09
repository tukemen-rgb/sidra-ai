"""Is 「描いて」 (draw) read as a make request, like 「書いて」 (write)?

C-1606. ``_MAKE_VERBS`` carried 「書いて」 but not its visual twin 「描いて」, so a
bare 「絵を描いて」「イラストを描いて」 was not recognised as a creation ask and fell to
the no-evidence answer that tells a maker to ingest a repository - the C-1261
mistake - while 「アートを描いて」 (a buildable ART request) was missed too. Adding
the verb routes a draw request to the honest decline (「いま作れるのは…アート…」)
or to ART when it names one, and a question about drawing is still a question.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DrawVerbResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service():
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.models.echo import EchoModelAdapter
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, QuarantineStore, SecurityGate

    tmp = Path(tempfile.mkdtemp(prefix="draw-verb-"))
    repo = "tukemen-rgb/site"
    settings = Settings(allowed_repositories=(repo,), data_dir=str(tmp / "sidra"))
    gate = SecurityGate(GatePolicy(), allowed_repositories=(repo,),
                        quarantine_store=QuarantineStore(tmp / "q.jsonl"))
    return SidraService(settings, model=EchoModelAdapter(),
                        store=DocumentStore(gate), gate=gate)


def evaluate_draw_verb_is_a_make_request() -> DrawVerbResult:
    from sidra_ai.creation.intent import CreationKind, detect_creation_intent

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # A bare draw request is a creation ask, declined by kind when it names no
    # buildable format.
    for req in ("絵を描いて", "イラストを描いて", "風景画を描いて"):
        it = detect_creation_intent(req)
        add(it.is_creation and it.kind is CreationKind.UNKNOWN,
            f"{req!r} not read as an (unknown-kind) creation ask")

    # A draw request that names a buildable format routes to it.
    add(detect_creation_intent("アートを描いて").kind is CreationKind.ART,
        "「アートを描いて」 did not route to ART")
    add(detect_creation_intent("壁紙を描いて").kind is CreationKind.ART,
        "「壁紙を描いて」 did not route to ART")

    # Non-regression: 作って still works, and a question about drawing stays a
    # question (not swept into creation).
    add(detect_creation_intent("螺旋のアートを作って").kind is CreationKind.ART,
        "作って regression on 「螺旋のアートを作って」")
    add(detect_creation_intent("絵はどう描かれますか").is_creation is False,
        "a question about drawing was swept into creation")
    add(detect_creation_intent("アートを描いてください").kind is CreationKind.ART,
        "polite 「アートを描いてください」 regressed")

    # End to end: 「絵を描いて」 is declined honestly, not sent to repo ingestion.
    answer = _service().chat("絵を描いて")["answer"]
    add("この形式は作れません" in answer,
        "「絵を描いて」 no longer gets the honest creation decline")
    add("取り込み" not in answer and "analyze" not in answer,
        "「絵を描いて」 still points a maker at repository ingestion (C-1261)")

    total = 10
    return DrawVerbResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DrawVerbResult", "evaluate_draw_verb_is_a_make_request"]
