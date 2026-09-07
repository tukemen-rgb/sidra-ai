"""Does a deck disclose evidence it left off every slide?

C-1478, the deck twin of the report's set-aside disclosure (C-1281).
``build_slides`` places a fact on the first section whose cue it matches and,
by design, leaves out a fact that matches no section's cue - a passage that does
not answer a heading must not sit under it. But that drop was silent: a deck
built from five retrieved facts could show two and quietly discard three, and
the artifact read as the whole sourced picture. The footer now discloses that
some evidence did not fit any slide - no figure, the same way the report
discloses its set-aside evidence - while a deck that placed everything, or was
handed nothing, says nothing.

The checks build real ``generate_deck`` outputs and read the HTML footer.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.decks import generate_deck, validate_deck
from sidra_ai.creation.evidence import Fact, NUMBER

_NOTE = "どのスライドにも当てはまらなかった根拠は載せていません"

# 課題1 + 解決1 place; the rest carry no section cue and no number, so they are
# left off every slide.
_MATCHED = [Fact("導入に時間がかかる課題がある。", "docs/a.md"),
            Fact("検索機能を実装して解決した。", "docs/b.md")]
_UNMATCHED = [Fact("チームは新しいオフィスへ移転した。", "docs/c.md"),
              Fact("創業者は元料理人である。", "docs/d.md"),
              Fact("ロゴの色を刷新した。", "docs/e.md")]
# four facts that all match only 課題 (no number, no other cue); the section
# keeps three, so the fourth is dropped.
_OVER_CAP = [Fact(f"{w}の課題がある。", f"docs/{w}.md")
             for w in ("運用", "設計", "保守", "移行")]


@dataclass(frozen=True)
class DeckOmittedFactsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_deck_discloses_omitted_facts() -> DeckOmittedFactsResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- some facts matched no slide: disclosed, on both outlines ---
    pitch = generate_deck("提案スライドを作って", facts=_MATCHED + _UNMATCHED, outline="pitch")
    add(_NOTE in pitch.html, "pitch: omitted facts not disclosed")
    status = generate_deck("週次進捗のスライドを作って", facts=_MATCHED + _UNMATCHED, outline="status")
    add(_NOTE in status.html, "status: omitted facts not disclosed")

    # the placed facts still appear (disclosure did not replace placement)
    body = "\n".join(b for s in pitch.slides for b in s.bullets)
    add(all(f.text[:10] in body for f in _MATCHED), "pitch: a placed fact went missing")

    # the disclosed deck still validates, and the note carries no digit
    verdict = validate_deck(pitch, _MATCHED + _UNMATCHED)
    add(verdict["usable"], f"pitch: disclosed deck no longer usable: {verdict['failures']}")
    note_line = next((ln for ln in pitch.html.splitlines() if _NOTE in ln), _NOTE)
    add(not NUMBER.findall(note_line.replace("SIDRA", "")), "disclosure note reprinted a digit")
    add(pitch.html.count(_NOTE) == 1, "disclosure note appears more than once")

    # --- nothing was dropped: no disclosure (no false claim) ---
    all_placed = generate_deck("提案スライドを作って", facts=_MATCHED, outline="pitch")
    add(_NOTE not in all_placed.html, "all-placed deck wrongly disclosed an omission")
    empty = generate_deck("提案スライドを作って", facts=[], outline="pitch")
    add(_NOTE not in empty.html, "empty deck wrongly disclosed an omission")

    # --- the per-section cap also counts as an omission ---
    capped = generate_deck("提案スライドを作って", facts=_OVER_CAP, outline="pitch")
    add(_NOTE in capped.html, "over-cap: the dropped 4th fact was not disclosed")
    capped_body = "\n".join(b for s in capped.slides for b in s.bullets)
    add(sum(f.text[:6] in capped_body for f in _OVER_CAP) == 3,
        "over-cap: the 課題 slide did not keep its three bullets")

    total = 10
    return DeckOmittedFactsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["DeckOmittedFactsResult", "evaluate_deck_discloses_omitted_facts"]
