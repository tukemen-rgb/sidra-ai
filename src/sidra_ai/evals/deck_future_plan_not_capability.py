"""Does a deck keep planned/future work off the current-capability slide?

C-1474, the future-plan twin of C-1461's negation guard. A status deck placed
「次はモバイル対応を予定している。」 under 「いま出来ること」 (what we can do now),
because the cue 「対応」 inside 「モバイル対応」 matched the capability section, which
is checked before the forward-looking slide. The planned item was presented as a
shipped capability, and 「残っていること」 was left an honest-looking blank though a
next step was given. The pitch outline had the same shape (「解決」 grabbed it via
「対応」 before 「次の一歩」).

A future marker (予定 / 今後 / これから) now keeps a fact off the capability
sections (解決 / いま出来ること), and 「残っていること」 recognises those markers, so
the fact lands on the forward-looking slide. A shipped fact (完了/実装/リリース済 -
all past) is unaffected, as is C-1461's negation guard.

The checks build a real ``generate_deck`` and read which slide holds each fact.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.evidence import Fact

_PLAN = Fact("次はモバイル対応を予定している。", "docs/roadmap.md")
_PLAN2 = Fact("今後は多言語対応を進める。", "docs/roadmap.md")
_PLAN3 = Fact("これから決済基盤を提供する。", "docs/roadmap.md")
_SHIPPED = Fact("決済連携の実装は完了し、本番に投入した。", "docs/status.md")
_SOLVED = Fact("検索の遅さに対応し、実装を終えた。", "docs/status.md")
_NEGATED = Fact("未対応の不具合が 3 件ある。", "docs/issues.md")


def _placement(request: str, facts: list[Fact], outline: str) -> dict[str, list[str]]:
    from sidra_ai.creation.decks import generate_deck

    deck = generate_deck(request, facts=facts, outline=outline)
    return {s.title: [b for b in s.bullets] for s in deck.slides}


def _in(fact: Fact, bullets: list[str]) -> bool:
    head = fact.text[:8]
    return any(head in b for b in bullets)


@dataclass(frozen=True)
class DeckFuturePlanResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_future_plan_not_capability() -> DeckFuturePlanResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- status outline ---
    st = _placement("週次進捗のスライドを作って",
                    [_SHIPPED, _PLAN, _PLAN2, _PLAN3, _NEGATED], "status")
    add(not _in(_PLAN, st.get("いま出来ること", [])), "status: 予定 fact on いま出来ること")
    add(not _in(_PLAN2, st.get("いま出来ること", [])), "status: 今後 fact on いま出来ること")
    add(not _in(_PLAN3, st.get("いま出来ること", [])), "status: これから fact on いま出来ること")
    add(_in(_PLAN, st.get("残っていること", [])), "status: 予定 fact not on 残っていること")
    add(_in(_SHIPPED, st.get("いま出来ること", [])), "status: shipped fact left いま出来ること")
    add(not _in(_NEGATED, st.get("いま出来ること", [])), "status: 未対応 on いま出来ること (C-1461)")

    # --- pitch outline ---
    pt = _placement("提案のスライドを作って", [_SOLVED, _PLAN, _PLAN3], "pitch")
    add(not _in(_PLAN, pt.get("解決", [])), "pitch: 予定 fact on 解決")
    add(not _in(_PLAN3, pt.get("解決", [])), "pitch: これから fact on 解決")
    add(_in(_PLAN, pt.get("次の一歩", [])), "pitch: 予定 fact not on 次の一歩")
    add(_in(_SOLVED, pt.get("解決", [])), "pitch: solved fact left 解決")

    total = 10
    return DeckFuturePlanResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckFuturePlanResult", "evaluate_deck_future_plan_not_capability"]
