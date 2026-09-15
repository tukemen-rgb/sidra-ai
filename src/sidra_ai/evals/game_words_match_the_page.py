"""Can the things a game page draws be asked for by name?

C-1855, found from §3 (lock and key). §3 itself checked out: the charm sits in
a one-tile chamber whose only opening is the optional door, the key needs the
cave's roamers dead, the chest needs the key AND the guardian, and the sealed
marks are a deliberate second route to the same key. The defect was at the
door of all that - naming the structure did not reach the template that has it.

``ADVENTURE_WORDS`` held nine entries and every one was a name for the GENRE
(ゼルダ, 冒険, ダンジョン, adventure...). Nothing the page actually contains was
in it, although the rooms are called 「森のはずれ / ひかり苔の洞窟 / 風の祭壇」 and
the tablet reads 「東の洞窟の敵が鍵を守っている。祭壇の宝を頼む」. So:

    「洞窟を探検するゲームを作って」
    → 「『洞窟』の題材を描く型はまだ無いため、代わりに既定の『タイミング釣り』型で
       作りました」

which is not a limitation honestly disclosed - it is false. The product draws
caves. C-1850 was the same shape one level down (a GIF motif with no words);
here the missing vocabulary makes the product deny a capability it has.

The boundary is the whole point, and it is the C-1121 rule seen from the other
side: a routing table that starts claiming genres this product does NOT build
is the same lie inverted. 「脱出ゲーム」 and 「RPG」 are deliberately absent, and
the words added are phrases rather than single kanji so that 「鍵盤のゲーム」 - an
instrument - is not read as a key.

Every word this checks is required to appear in the generated page, so the
eval cannot pass by agreeing with a vocabulary that has drifted from what the
page draws.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.games import choose_template, generate_game

#: Requests naming what the adventure page holds, and the template that holds
#: it. Each was measured going to the fishing default on 2026-09-15.
PAGE_REQUESTS: tuple[tuple[str, str], ...] = (
    ("鍵と扉のあるゲームを作って", "adventure"),
    ("鍵を探して扉を開けるゲームを作って", "adventure"),
    ("洞窟を探検するゲームを作って", "adventure"),
    ("宝探しのゲームを作って", "adventure"),
    ("宝箱のゲームを作って", "adventure"),
    ("迷宮のゲームを作って", "adventure"),
    ("祭壇のゲームを作って", "adventure"),
    ("謎解きのゲームを作って", "puzzle"),
)

#: Words that must NOT reach these templates. 「鍵盤」 is an instrument;
#: 「脱出」 and 「RPG」 are genres this product does not build, and claiming
#: them would be this item's own defect pointing the other way (C-1121).
NOT_OURS: tuple[str, ...] = (
    "鍵盤のゲームを作って",
    "脱出ゲームを作って",
    "RPGを作って",
)

#: The routing this product already had, which adding words must not disturb.
SETTLED: tuple[tuple[str, str], ...] = (
    ("ゲームを作って", "fishing"),
    ("フルーツキャッチを作って", "catch"),
    ("玉転がしゲームを作って", "marble"),
    ("レースゲームを作って", "racing"),
    ("ジャンプで進むゲームを作って", "platformer"),
    ("パズルゲームを作って", "puzzle"),
    ("巨大怪獣と戦うゲームを作って", "kaiju"),
    ("光線で撃ち合う対戦ゲームを作って", "duel"),
    ("シューティングゲームを作って", "shooter"),
    ("迷宮を冒険するゲームを作って", "adventure"),
    ("テトリスを作って", "fishing"),
    ("対戦格闘ゲームを作って", "fishing"),
)

#: The words that have to be visible in the page itself, so that what the
#: table offers and what the generator draws cannot drift apart.
ON_THE_PAGE: tuple[str, ...] = ("洞窟", "祭壇", "宝箱", "鍵")


@dataclass(frozen=True)
class GameWordsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_game_words_match_the_page() -> GameWordsResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) naming what the page holds reaches the page ------------------
    wrong = {
        request: choose_template(request)
        for request, want in PAGE_REQUESTS
        if choose_template(request) != want
    }
    add(not wrong, f"A: these did not reach their template: {wrong}")

    # --- (B) and the answer stops saying no such template exists ----------
    #     The sentence is the defect: a miss that says 「まだ無い」 about a
    #     thing the product draws is worse than the miss.
    page = generate_game("洞窟を探検するゲームを作って")
    add(page.template == "adventure",
        f"B: the cave request built {page.template}")

    # --- (C) the words are really on the page -----------------------------
    #     Read from the generated HTML, not asserted from the table: this is
    #     what stops the vocabulary drifting away from what is drawn.
    html = page.html
    missing = [word for word in ON_THE_PAGE if word not in html]
    add(not missing, f"C: offered but not drawn: {missing}")

    # --- (D) what this product does not build, it still does not claim ----
    claimed = {
        request: choose_template(request)
        for request in NOT_OURS
        if choose_template(request) in ("adventure", "puzzle")
    }
    add(not claimed, f"D: a genre this product lacks was claimed: {claimed}")

    # --- (E) nothing that already worked moved ----------------------------
    moved = {
        request: (want, choose_template(request))
        for request, want in SETTLED
        if choose_template(request) != want
    }
    add(not moved, f"E: settled routing moved: {moved}")

    return GameWordsResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
