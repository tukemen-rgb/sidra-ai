"""Is 「作ったものを一覧で見せて」 answered with the list, or with the index?

C-1844. Driven as an ordinary conversation - greeting, 「何ができるの？」, make a
game, make it harder - everything held until the operator asked to see what
had been made, and that was answered 「現時点では十分な根拠がありません…対象リポ
ジトリの取り込みを管理者に依頼してください」. The question was about files this
product had written a moment earlier.

The sixth and last of the family: greeting (C-1796), help (C-1802), a change
with no target (C-1797), an unreadable change (C-1814), the wrong kind
(C-1835), and saying so in one step (C-1837).

This eval also holds the regression found while writing it, which is the more
serious half. C-1837 - mine, two cycles back - widened the revision kind check
to messages with no referent, and 「して」 is a change verb that sits inside
探して, 確認して, 要約して. Six of nine ordinary corpus questions that mentioned
an artifact kind were being answered 「いま修正できるのはゲームだけ」.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: Ordinary corpus questions that name a kind of artifact. None of them asks
#: for a change, and none may be answered as one.
CORPUS_QUESTIONS: tuple[str, ...] = (
    "使い方のドキュメントを探して",
    "収益化のレポートを探して",
    "設計のドキュメントを確認して",
    "スライドの内容を要約して",
    "レポートの結論を説明して",
    "3Dモデルの形式を確認して",
)


@dataclass(frozen=True)
class ArtifactListResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service() -> tuple[SidraService, Path]:
    root = Path(scratch_dir("sidra-c1844-"))
    return (
        SidraService(
            Settings(data_dir=str(root), model_backend="echo"),
            state_store=StateStore(root / "state.json"),
        ),
        root,
    )


def evaluate_artifact_list_is_answered() -> ArtifactListResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service, root = _service()

    # --- (A) with nothing made, it says so ---------------------------------
    empty = service.chat("作ったものを一覧で見せて")
    add(empty.get("refusal") == "artifact_list"
        and "まだ何も作っていません" in (empty.get("answer") or ""),
        f"A: an empty listing answered {empty.get('refusal')!r}")
    # --- (B) and names what can be made, from the live registry ------------
    add("ゲーム" in (empty.get("answer") or ""),
        "B: the empty listing does not say what can be made")

    # Seven, not three: the cap is five, and the rule being held is C-1680's -
    # show some, report the true total. With three artifacts a version that
    # reports what it shows is indistinguishable from one that reports what
    # exists, and a sabotage doing exactly that scored a perfect run.
    for request in (
        "猫のゲームを作って",
        "魚のGIFを作って",
        "海のアートを作って",
        "犬のゲームを作って",
        "船の3Dモデルを作って",
        "鳥のGIFを作って",
        "空のアートを作って",
    ):
        service.chat(request)

    listed = service.chat("作ったものを一覧で見せて")
    answer = listed.get("answer") or ""
    # --- (C) the answer is the list, not the abstention --------------------
    add(listed.get("refusal") == "artifact_list"
        and "十分な根拠がありません" not in answer,
        f"C: answered {listed.get('refusal')!r}")
    # --- (D) it names the files the listing itself would name --------------
    #     Against list_artifacts rather than the directory: the game writes a
    #     .meta.json beside its page for the revision feature, and the listing
    #     does not count that as something the operator made. Counting raw
    #     files here made this eval demand a total the product is right not to
    #     report - measured while writing it.
    from sidra_ai.api.artifacts import list_artifacts

    listing = list_artifacts(root)
    named = [artifact.name for artifact in listing if artifact.name in answer]
    add(len(named) >= 3, f"D: the answer names {len(named)} of {len(listing)} artifacts")
    # --- (E) and reports the true total, having shown fewer ----------------
    add(len(listing) > len(named)
        and f"全 {len(listing)} 件" in answer,
        f"E: {len(listing)} made, {len(named)} named, and the answer says "
        f"{'the total' if f'全 {len(listing)} 件' in answer else 'something else'}")
    # --- (F) no file content rides along -----------------------------------
    #     The listing endpoint carries no preview because a deck's body is
    #     retrieved content; the same holds here (app.py's rule).
    game = next((path for path in (root / "artifacts").glob("game-*.html")), None)
    body = game.read_text(encoding="utf-8")[:2000] if game else ""
    add(bool(body) and not any(line in answer for line in body.splitlines() if len(line) > 40),
        "F: a line of the artifact's body reached the answer")
    # --- (G) a real corpus question is still a question --------------------
    #     C-1837 made six of these into 「修正できるのはゲームだけ」 because 「して」
    #     is a change verb and 探して ends in it.
    refused_as_revision = [
        question
        for question in CORPUS_QUESTIONS
        if service.chat(question).get("refusal") == "revision_kind"
    ]
    add(not refused_as_revision,
        f"G: corpus questions answered as revisions: {refused_as_revision[:3]}")
    # --- (H) and revisions still work --------------------------------------
    add(service.chat("さっきのゲームを難しくして").get("refused") is False
        and service.chat("さっきのGIFを難しくして").get("refusal") == "revision_kind"
        and service.chat("もっと難しくして").get("refusal") == "revision_target",
        "H: the revision paths changed")
    # --- (I) a question that merely contains these words is not a listing --
    add(service.chat("作ったものの一覧をドキュメントから探して").get("refusal")
        != "artifact_list",
        "I: a corpus query was swallowed by the listing rule")

    return ArtifactListResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "ArtifactListResult",
    "CORPUS_QUESTIONS",
    "evaluate_artifact_list_is_answered",
]
