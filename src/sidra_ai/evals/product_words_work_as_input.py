"""Do the page's own words work when somebody types them back?

C-1881, two families measured on the real service.

**(1) The noun form of a button.** The page's button says 「結果をコピー」. The
cue list held the verb stem 「コピーし」, which a noun phrase never contains, so
「さっきのゲームの結果のコピーってどうやるの」 got the abstention that asks an
administrator to ingest a repository - while 「共有ってできるの」 was answered.

**(2) A new title, given the way people give one.** 「タイトルを「共有の記録」に
して」 works because 「して」 is a change verb. 「…「共有の記録」に」,
「…「今日の挑戦」へ」 and 「…「自己ベストの道」でお願いします」 carry no verb, were
not revisions, and fell to the branch that answers questions about the page -
where **the words of the requested title chose the answer**: asking to name a
page 「今日の挑戦」 produced a lecture about 今日の挑戦.

Both are the family C-1797, C-1814, C-1835, C-1866 and C-1875 have each taken
one case out of: somebody talking about the thing this product made, sent to
the index.

**The half that matters is the other one.** Widening a detector is easy and
the cost lands somewhere else - C-1878 exists because a branch grabbed
revision instructions, and C-1844 because a substring rule swallowed corpus
questions. So the refusals are measured here at the same weight as the
acceptances: a question about a title is not a rename, a creation request is
not a rename, and a corpus question that happens to quote a title is a corpus
question.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO = "tukemen-rgb/sidra-ai"
_WALL = ("十分な根拠がありません", "analyze")


@dataclass(frozen=True)
class ProductWordsResult:
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
                content=f"第 {i} 章。収益化の方針と審査の基準について。" + "掲載順は売らない。" * 8,
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
    settings = Settings(data_dir=home, model_backend="echo", allowed_repositories=(_REPO,))
    return SidraService(
        settings, store=store, gate=gate, state_store=StateStore(Path(home) / "state.json")
    )


def _after_making_a_game(message: str) -> dict:
    with tempfile.TemporaryDirectory() as home:
        service = _service(home)
        first = service.chat("レースゲームを作って")
        history = [("レースゲームを作って", first.get("answer") or "")]
        return service.chat(message, history=history)


def _hit_the_wall(answer: str) -> bool:
    return all(part in answer for part in _WALL)


#: (1) The page's own words, as a noun. The control is the phrasing that
#: already worked - without it, a fix that broke the working case would still
#: score full marks here.
_ASKED_ABOUT: tuple[tuple[str, str], ...] = (
    ("さっきのゲームの結果のコピーってどうやるの", "結果をコピー"),
    ("さっきのゲームの結果をコピーはどうやるの", "結果をコピー"),
    ("さっきのゲームの共有ってできるの", "結果をコピー"),
)

#: (2) A new title, with no change verb. The last is the phrasing that already
#: worked, for the same reason.
_RENAMES: tuple[tuple[str, str], ...] = (
    ('さっきのゲームのタイトルを「共有の記録」に', "共有の記録"),
    ('さっきのゲームの名前を「今日の挑戦」へ', "今日の挑戦"),
    ('さっきのゲームのタイトル「自己ベストの道」でお願いします', "自己ベストの道"),
    ('さっきのゲームのタイトルを「共有の記録」にして', "共有の記録"),
)

#: ...and what a wider detector must still refuse.
_NOT_RENAMES: tuple[tuple[str, str], ...] = (
    ('さっきのゲームのタイトルは「共有の記録」ですか', "a question about the title"),
    ('さっきのゲームのタイトル「自己ベストの道」の意味は', "asking what a title means"),
    ('さっきのゲームのタイトルを教えて', "asking what the title is"),
    ('「共有の記録」というタイトルのゲームを作って', "a creation request"),
    ('タイトルに「共有の記録」と書いてある資料を探して', "a corpus question"),
)


def evaluate_product_words_work_as_input() -> ProductWordsResult:
    from sidra_ai.creation.revise import detect_revision_intent

    failures: list[str] = []
    passed = 0

    for message, expected in _ASKED_ABOUT:
        answer = (_after_making_a_game(message).get("answer") or "").replace("\n", " ")
        if _hit_the_wall(answer):
            failures.append(f"「{message}」 reaches the index wall")
        elif expected not in answer:
            failures.append(f"「{message}」 was answered without 「{expected}」: {answer[:60]}")
        else:
            passed += 1

    for message, title in _RENAMES:
        out = _after_making_a_game(message)
        answer = (out.get("answer") or "").replace("\n", " ")
        if _hit_the_wall(answer):
            failures.append(f"「{message}」 reaches the index wall")
        elif f"タイトル「{title}」" not in answer:
            failures.append(f"「{message}」 did not rename the page: {answer[:70]}")
        else:
            passed += 1

    for message, why in _NOT_RENAMES:
        intent = detect_revision_intent(message)
        if intent.adjustments.get("title") is not None:
            failures.append(
                f"「{message}」 was read as a rename to "
                f"「{intent.adjustments['title']}」 ({why})"
            )
        else:
            passed += 1

    # ...and an ordinary corpus question that merely contains the cue word is
    # still answered from the corpus. 「コピー」 on its own belongs to plenty of
    # documents, which is why the cues are the two noun phrases the button
    # actually prints.
    #
    # Deliberately naming no source: the first version of this check asked
    # 「…をドキュメントから探して」, and 「ドキュメント」 trips the `_CORPUS_SOURCES`
    # veto before any cue is consulted - so a probe that widened the cue to a
    # bare 「コピー」 scored full marks. The dangerous case is the corpus
    # question that names nowhere to look, because only the cue stands between
    # it and the page branch.
    for corpus_question in (
        "コピーライトの方針を教えて",
        "審査の基準のコピーはどこにありますか",
    ):
        corpus = (_after_making_a_game(corpus_question).get("answer") or "").replace("\n", " ")
        if "結果をコピー" in corpus:
            failures.append(
                f"「{corpus_question}」 was answered about the page: {corpus[:70]}"
            )
        else:
            passed += 1

    return ProductWordsResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=len(_ASKED_ABOUT) + len(_RENAMES) + len(_NOT_RENAMES) + 2,
        failures=tuple(failures),
    )
