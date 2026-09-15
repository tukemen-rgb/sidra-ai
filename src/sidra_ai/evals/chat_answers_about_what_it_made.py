"""Asked about the page it just made, does the product answer?

C-1866, from §8. §8's own 学び said the three retention paths - come back,
come back tomorrow, show someone - were 「丸ごと欠けている」, and they are not:
result copy (C-1110), the daily board (C-1107), skins (C-1109), the personal
best and its ghost (C-1401) are all shipped, and the share line even honours
事実 7's rule that no URL goes in it. What was missing was an answer.

Measured on 2026-09-15, one turn after 「魚釣りゲームを作って」: six questions,
six times the no-evidence abstention that asks for a repository to be ingested.
So the product built the page, knows its template, knows what that page can do,
and sent the reader to the corpus wall.

``_ARTIFACT_LIST_QUERIES`` records the lineage of that reply - C-1796, C-1802,
C-1797, C-1814, C-1835, C-1837, and C-1861 each removed it from one place.
This is the next one, and the last of them that is a *question* rather than an
instruction.

Both directions, and the boundary is the hard part:

* the six phrasings are answered, naming what that template actually ships;
* a template without the ghost is not told it has one;
* somebody who has made nothing keeps the evidence answer - describing "your
  page" to a person with no page would be this defect pointing the other way;
* a real corpus question is not swallowed, even when it contains 「共有」 or
  「記録」. Measured while writing this: 「共有ポリシーについてドキュメントから
  探して」 WAS swallowed, which is what C-1844 avoided by matching whole
  messages and the price of matching substrings here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.ghost import GHOST_TEMPLATES
from sidra_ai.creation.share import share_spec
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: One per way a person asks about the page, each measured wrong.
FEATURE_QUESTIONS: tuple[str, ...] = (
    "スコアを自慢したい",
    "結果をコピーしたい",
    "今日の挑戦って何",
    "見た目を変えたい",
    "自己ベストは残る？",
    "友達に見せたい",
)

#: Questions that name where to look: about the corpus, whatever else they say.
CORPUS_QUESTIONS: tuple[str, ...] = (
    "共有ポリシーについてドキュメントから探して",
    "資料の共有について教えて",
    "リポジトリの記録は残る？",
)

_CODE = "artifact_feature_question"


@dataclass(frozen=True)
class AnswersAboutResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(prefix: str) -> tuple[SidraService, Path]:
    root = Path(scratch_dir(prefix))
    return (
        SidraService(
            Settings(data_dir=str(root), model_backend="echo"),
            state_store=StateStore(root / "state.json"),
        ),
        root,
    )


def evaluate_chat_answers_about_what_it_made() -> AnswersAboutResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) nothing made yet: the evidence answer stands ------------------
    #     First, because describing a page to somebody who has none is this
    #     item's own defect pointing the other way.
    empty, _ = _service("c1866-empty-")
    add(empty.chat("スコアを自慢したい").get("refusal") != _CODE,
        "A: described a page to somebody who had not made one")

    service, root = _service("c1866-fishing-")
    service.chat("魚釣りゲームを作って")
    before = {path.name for path in (root / "artifacts").iterdir()}
    answers = {q: service.chat(q) for q in FEATURE_QUESTIONS}
    after = {path.name for path in (root / "artifacts").iterdir()}

    # --- (B) every phrasing is answered ------------------------------------
    wrong = {q: r.get("refusal") for q, r in answers.items()
             if r.get("refusal") != _CODE}
    add(not wrong, f"B: still sent elsewhere: {wrong}")

    # --- (C) and nothing was written by a question -------------------------
    add(before == after, f"C: a question changed files: {sorted(after ^ before)}")

    # --- (D) the answer names what this page actually has -------------------
    #     Read from the page's own tables: an answer built from a list here
    #     would agree with itself while the page moved on.
    spec = share_spec("fishing")
    brag = answers["スコアを自慢したい"].get("answer") or ""
    add(spec["name"] in brag and spec["emoji"] in brag,
        f"D: the share answer does not use this template's own row: {brag[:70]}")
    add("URL" in brag,
        "D: the answer does not say the share text carries no URL (§8 事実 7)")

    # --- (E) a feature this template does NOT have is not claimed ----------
    add("fishing" not in GHOST_TEMPLATES, "E: the fixture template gained a ghost")
    add("ゴースト" not in (answers["自己ベストは残る？"].get("answer") or ""),
        "E: a template without the ghost was told it has one")
    racing, _ = _service("c1866-racing-")
    racing.chat("レースゲームを作って")
    add("ゴースト" in (racing.chat("自己ベストは残る？").get("answer") or ""),
        "E: the template that HAS the ghost was not told about it")

    # --- (F) a corpus question is still a corpus question -------------------
    for question in CORPUS_QUESTIONS:
        got = service.chat(question).get("refusal")
        add(got != _CODE, f"F: swallowed a corpus question: {question!r}")

    # --- (G) the neighbouring paths are untouched ---------------------------
    add(service.chat("さっきのゲームを難しくして").get("refused") is False,
        "G: a genuine revision stopped working")
    add(service.chat("さっきのゲームを消して").get("refusal") == "delete_unsupported",
        "G: the deletion answer changed")
    add(service.chat("さっきのゲームの音量を下げて").get("refusal") == "panel_setting",
        "G: the panel answer changed")

    return AnswersAboutResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
