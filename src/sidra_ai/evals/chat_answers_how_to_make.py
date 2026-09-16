"""Does "how do I make a report?" get an answer, or the index wall?

C-1875. 「使い方を教えて」 is answered from the live generator registry (C-1802);
「レポートの作り方を教えて」 - the same question about the same product, one
phrasing away - reached the no-evidence abstention that asks an administrator
to ingest a repository. Measured on the real ``chat`` before anything was
changed, all four of these hit that wall:

    レポートの作り方を教えて
    ゲームの作り方を教えて
    スライドの作り方を教えて
    どうやってレポートを作るの

The same family as C-1866: asked about something the product has, sent to the
index. C-1866 is about the page that was made; this is about making one at
all, so it deliberately does not require an artifact to exist - somebody
asking before they make anything is the reader it is for.

**Both directions, in one judge.** A branch that answers every message with
the product's menu would pass the first half and wreck the product, so the
second half is here too and is worth more than the first: a question that
names where to look is still a corpus question, a subject the product does
not make is still a corpus question, and 「レースゲームを作って」 still makes a
game rather than being told how to.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO = "tukemen-rgb/sidra-ai"

#: The reply this item exists to stop: the abstention that names the ingest
#: endpoint. Matched on both halves so a reworded abstention still counts.
_WALL = ("十分な根拠がありません", "analyze")


@dataclass(frozen=True)
class HowToMakeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(home: str):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.ingestion.state import StateStore
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    for i in range(6):
        store.add(
            Document(
                content=(
                    f"第 {i} 章。収益化の方針と審査の基準について。"
                    + "掲載順は売らない。" * 8
                ),
                provenance=Provenance(
                    source="github",
                    repository=_REPO,
                    path=f"docs/p{i}.md",
                    commit_sha="0" * 40,
                    timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )
    settings = Settings(
        data_dir=home, model_backend="echo", allowed_repositories=(_REPO,)
    )
    return SidraService(
        settings,
        store=store,
        gate=gate,
        state_store=StateStore(Path(home) / "state.json"),
    )


def _ask(message: str) -> dict:
    """One message against a fresh service, so no case sees another's state."""

    with tempfile.TemporaryDirectory() as home:
        return _service(home).chat(message)


def _hit_the_wall(answer: str) -> bool:
    return all(part in answer for part in _WALL)


#: Answered by naming what can be made. Four phrasings, because the phrasing is
#: the whole defect - 「どうやってレポートを作るの」 in particular puts the subject
#: between the question word and the verb, which is how people actually ask and
#: which a contiguous cue missed when this was first written.
_ANSWERED: tuple[tuple[str, str, str], ...] = (
    ("レポートの作り方を教えて", "レポート", "犬のレポートを作って"),
    ("ゲームの作り方を教えて", "ゲーム", "レースゲームを作って"),
    ("スライドの作り方を教えて", "スライド", "新製品のスライドを作って"),
    ("どうやってレポートを作るの", "レポート", "犬のレポートを作って"),
)

#: ...and what must not change. Worth more than the four above: the cheap way
#: to pass those is to answer everything with the menu.
_UNTOUCHED: tuple[tuple[str, str], ...] = (
    ("カレーの作り方を教えて", "a subject this product does not make"),
    ("レポートの作り方をドキュメントから探して", "names a source, so it is a corpus question"),
    ("ゲームの作り方をリポジトリから探して", "names a source, so it is a corpus question"),
)


def evaluate_chat_answers_how_to_make() -> HowToMakeResult:
    failures: list[str] = []
    passed = 0

    for message, label, example in _ANSWERED:
        answer = (_ask(message).get("answer") or "").replace("\n", " ")
        if _hit_the_wall(answer):
            failures.append(f"「{message}」 still reaches the index wall")
        elif label not in answer:
            failures.append(f"「{message}」 was answered without naming {label}: {answer[:60]}")
        elif example not in answer:
            # The part a menu cannot supply. Naming the kind is satisfied by
            # the 「ほかに作れるのは …」 list, which names every kind - measured:
            # a probe that stripped the kind from the opening sentence still
            # passed the check above. A worked sentence for the kind asked is
            # the thing the asker can actually send.
            failures.append(
                f"「{message}」 got no worked example for {label}: {answer[:70]}"
            )
        else:
            passed += 1

    for message, why in _UNTOUCHED:
        answer = (_ask(message).get("answer") or "").replace("\n", " ")
        if not _hit_the_wall(answer):
            failures.append(
                f"「{message}」 was swallowed by the how-to branch ({why}): {answer[:60]}"
            )
        else:
            passed += 1

    # ...and the request that makes something still makes it. A branch placed
    # one line too early would turn every 「…を作って」 into advice about how to
    # ask for it, and nothing above would notice.
    made = _ask("レースゲームを作って")
    made_answer = (made.get("answer") or "").replace("\n", " ")
    if made.get("refusal") == "how_to_make" or "作りました" not in made_answer:
        failures.append(f"a real creation request no longer creates: {made_answer[:70]}")
    else:
        passed += 1

    return HowToMakeResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=len(_ANSWERED) + len(_UNTOUCHED) + 1,
        failures=tuple(failures),
    )
