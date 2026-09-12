"""Does a revision 'not found' reply say when its title list was truncated?

C-1727. When a revision names a game that matches nothing, ``build_game_reviser``
replies 「その名前のゲームは見つかりません。あるのは「A」…です。どれを修正するか、
名前で指定してください」 - a definitive list of what exists, so the operator can
pick the right one. But the list is capped at 5 titles and the rest are dropped
silently: an operator with 8 games is told 「あるのは <5>」 as if those were all,
and if the game they meant is one of the other 3 it is not even shown - the exact
"specify by name" guidance defeated. The conversation-scoped variant
（「この会話で作った「A」…が見つかりません」） caps the same way. Both now disclose how
many more there are - the honesty the flat listing (C-1680) and a clipped excerpt
(C-1264) already keep.

The checks drive the real reviser: a >5-game not-found reply names 5 and discloses
the remainder, a reply at or under 5 gets no disclosure and its wording is
unchanged, and the conversation-scoped variant discloses the remainder too.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass


def _reviser_with_games(titles: list[str]):
    from sidra_ai.creation.games import generate_game, save_game
    from sidra_ai.creation.revise import build_game_reviser, save_meta

    data_dir = tempfile.mkdtemp()
    for title in titles:
        game = generate_game("シューティングゲームを作って")
        path = save_game(game, data_dir)
        save_meta(path, request=title, template=game.template,
                  difficulty=game.difficulty, theme="void", title=title)
    return build_game_reviser(data_dir)


def _history(titles: list[str]) -> list[tuple[str, str]]:
    return [(f"{t}ゲームを作って", f"「{t}」を作りました（難易度 normal）。") for t in titles]


def _not_found_summary(machine_titles: list[str], history=None):
    from sidra_ai.creation.revise import RevisionIntent

    reviser = _reviser_with_games(machine_titles)
    # A genre-naming revision that matches no game on the machine -> not found.
    intent = RevisionIntent(is_revision=True, adjustments={"difficulty": "+1"})
    return reviser("レースのゲームを難しくして", intent, history).summary


@dataclass(frozen=True)
class RevisionListResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_revision_not_found_lists_all_titles() -> RevisionListResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    eight = [f"ゲーム{i}番" for i in range(8)]
    big = _not_found_summary(eight)

    # --- (A) the machine-titles branch still lists titles and reads as before ---
    add("見つかりません" in big and "あるのは" in big, f"A: the not-found wording regressed: {big!r}")

    # --- (B) the remainder is disclosed (8 exist, 5 shown -> 3 more) ---
    add("ほか 3 件" in big,
        f"B: the remainder (ほか 3 件) was not disclosed for 8 titles: {big!r}")

    # --- (C) exactly the 5 newest are named and the cap holds (6th not listed) ---
    add("ゲーム3番" in big and "ゲーム2番" not in big,
        f"C: the 5-title cap did not hold (5th missing or 6th listed): {big!r}")

    # --- (D) a 5-game list gets no disclosure (not over-eager) ---
    five = _not_found_summary([f"ゲーム{i}番" for i in range(5)])
    add("ほか" not in five and "他" not in five, f"D: a 5-title list got a spurious remainder: {five!r}")

    # --- (E) the conversation-scoped variant discloses its remainder too ---
    # 7 remembered titles, none on the machine -> the "この会話で作った" branch.
    conv = _not_found_summary(["別のゲーム"], history=_history([f"会話ゲーム{i}" for i in range(7)]))
    add("この会話で作った" in conv and "ほか 2 件" in conv,
        f"E: the conversation-scoped remainder (ほか 2 件) was not disclosed: {conv!r}")

    # --- (F) a single remembered title keeps the exact legacy wording ---
    one = _not_found_summary(["別のゲーム"], history=_history(["将棋"]))
    add("この会話で作った「将棋」が見つかりません" in one and "ほか" not in one,
        f"F: a single-title conversation reply changed: {one!r}")

    total = 6
    return RevisionListResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["RevisionListResult", "evaluate_revision_not_found_lists_all_titles"]
