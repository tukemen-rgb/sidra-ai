"""Does a change asked of a slide edit a slide - or the latest game?

C-1835. Revision is game-only: :mod:`sidra_ai.creation.revise` reads
``game-*.meta.json`` and nothing else. Nothing asked what the message called
the thing, so 「さっきのGIFを難しくして」 resolved 「さっきの」 to the latest game and
edited it - measured, a GIF request moved a game from normal to hard and
answered 「「猫」を修正しました: 難易度 normal→hard」, success under the game's own
title.

The subject rules one module over already argue this case: a word that can
point at a page can also name one that is not there (C-1511b, C-1513), and
such a message is refused rather than resolved to whatever is nearest. Kinds
had no such rule.

The check that matters is not the wording but the file: this eval reads the
game's own metadata before and after, because an eval that only reads the
answer would pass a version that apologises and edits anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import detect_revision_intent
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore


@dataclass(frozen=True)
class RevisionKindResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(root: Path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )


def _game_state(root: Path) -> dict[str, str]:
    """Every game's difficulty, keyed by file - the thing a wrong edit moves."""

    return {
        path.name: json.loads(path.read_text(encoding="utf-8")).get("difficulty", "")
        for path in sorted((root / "artifacts").glob("game-*.meta.json"))
    }


def evaluate_revision_refuses_another_kind() -> RevisionKindResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("sidra-c1835-"))
    service = _service(root)
    service.chat("猫のゲームを作って")
    service.chat("魚のGIFを作って")
    service.chat("新商品のスライドを作って")

    before = _game_state(root)
    gif = service.chat("さっきのGIFを難しくして")
    after_gif = _game_state(root)

    # --- (A) the game is not touched -------------------------------------
    add(after_gif == before,
        f"A: a GIF request changed the game: {before} -> {after_gif}")
    # --- (B) and it is refused as a change, not as a failed search --------
    add(gif.get("refused") is True and gif.get("refusal") == "revision_kind",
        f"B: the GIF request was answered as {gif.get('refusal')!r}")
    # --- (C) the answer names the kind they asked about -------------------
    #     A sentence about games, sent to someone who said GIF, reads as an
    #     answer to a different question.
    add("GIF" in (gif.get("answer") or ""),
        "C: the refusal never mentions the kind that was named")
    # --- (D) a slide whose change is unreadable hears the same thing ------
    #     This used to list what a *game* can change (難易度・テーマ…) without
    #     ever saying a slide cannot be changed at all.
    deck = service.chat("さっきのスライドを短くして")
    add(deck.get("refusal") == "revision_kind" and "スライド" in (deck.get("answer") or ""),
        f"D: the slide request was answered as {deck.get('refusal')!r}")
    # --- (E) the real thing still works ----------------------------------
    game = service.chat("さっきのゲームを難しくして")
    after_game = _game_state(root)
    add(game.get("refused") is False and after_game != before,
        "E: a genuine game revision stopped working")
    # --- (F) a message that names no kind is unchanged --------------------
    #     「さっきのを難しくして」 has always meant the latest game, and this
    #     change must not make the referent rules stricter.
    add(detect_revision_intent("さっきのを難しくして").is_revision
        and detect_revision_intent("それを簡単にして").is_revision,
        "F: a change with no kind named stopped being a revision")
    # --- (G) every other kind is covered, not just the two driven above ---
    kinds = {
        request: detect_revision_intent(request).names_other_kind
        for request in (
            "さっきのアートを明るくして",
            "さっきのレポートを難しくして",
            "さっきの3Dモデルを大きくして",
        )
    }
    add(all(kinds.values()),
        f"G: some kinds still resolve to the latest game: {kinds}")
    # --- (H) and the page's own title is not part of the decision ---------
    #     「さっきのゲームの資料を直して」 names a document last, and the head
    #     noun of a Japanese phrase comes last (C-1479), so it is a document.
    add(detect_revision_intent("さっきのゲームの資料を直して").names_other_kind != ""
        and detect_revision_intent("さっきの資料のゲームを難しくして").is_revision,
        "H: the latest-match reading was lost")

    # --- (I) the answer arrives in one step -------------------------------
    #     C-1837 rewrote this check, and the reason is worth keeping. It used
    #     to pin the opposite: that 「GIFを難しくして」 should ask for 「さっきの」
    #     first, because C-1797 owns a change with no referent. Driving it
    #     showed what that costs - the reader follows the advice, sends
    #     「さっきのGIFを難しくして」, and only then hears that GIFs cannot be
    #     revised at all. C-1814 named exactly that failure ("the product's
    #     own advice did not work on the product"), and the cycle citing it
    #     rebuilt it. The check had measured the implementation, not the
    #     behaviour.
    #
    #     What is pinned is the step count: the first answer already says
    #     revision is game-only. The sentence may still mention 「さっきのゲーム
    #     を難しくして」 - that is the example of what *can* be revised, not an
    #     instruction to come back with the same request reworded.
    one_step = service.chat("GIFを難しくして")
    add(one_step.get("refusal") == "revision_kind"
        and "ゲームだけ" in (one_step.get("answer") or ""),
        f"I: the first answer does not say revision is game-only: "
        f"{one_step.get('refusal')!r}")
    # --- (J) a change that is neither pointed at nor readable --------------
    #     The fourth corner of this family. C-1797 covers "change known,
    #     target missing", C-1814 "target known, change unreadable", C-1835
    #     "target known, wrong kind" - and 「スライドを短くして」 has none of
    #     them, so it fell to the no-evidence boilerplate that asks for a
    #     repository to be ingested.
    fourth = service.chat("スライドを短くして")
    add(fourth.get("refusal") == "revision_kind",
        f"J: 「スライドを短くして」 was answered as {fourth.get('refusal')!r}")
    # --- (K) and C-1797 still owns the case that is really about a target --
    add(service.chat("もっと難しくして").get("refusal") == "revision_target",
        "K: a change naming no kind stopped asking which artifact is meant")

    # --- (L) only a change instruction reaches this at all ----------------
    #     Widening the kind check to messages with no referent leaves the
    #     change-verb gate as the only thing that keeps a plain mention of a
    #     kind out of it. The first version of this check drove
    #     「スライドの作り方を教えて」 and 「スライドを作って」, and a sabotage that
    #     removed the gate still scored full marks - those two are held by the
    #     question and creation vetoes further up, not by the gate.
    #
    #     Measured which messages the gate actually decides: 「レポートの内容」,
    #     「スライドについて」, 「GIFのループ」, 「スライドの枚数」 - a kind named with
    #     no change verb anywhere. Without the gate every one of them is
    #     answered 「修正できるのはゲームだけ」, which for 「レポートの内容」 is a
    #     refusal to a question nobody asked as a change.
    mention = service.chat("レポートの内容")
    asked = service.chat("スライドの作り方を教えて")
    built = service.chat("スライドを作って")
    add(mention.get("refusal") != "revision_kind"
        and asked.get("refusal") != "revision_kind"
        and built.get("refusal") != "revision_kind"
        and (built.get("creation") or {}).get("outcome", {}).get("handled") is True,
        f"L: a mention, a question or a creation request was answered as a "
        f"revision: {mention.get('refusal')!r} / {asked.get('refusal')!r} / "
        f"{built.get('refusal')!r}")

    return RevisionKindResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "RevisionKindResult",
    "evaluate_revision_refuses_another_kind",
]
