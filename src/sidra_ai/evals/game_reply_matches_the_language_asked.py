"""Does making a game answer in the language it was asked in?

C-1929 brought the product's own rule - `_reply_in_japanese`, 「SYSTEM_PROMPT
rule 6, the language a reply takes」 - to the revision lane. Making a game is
the main function, and English requests have routed since C-1516, so this
path answered in the wrong language for far longer: 「make a racing game」
built the game and said 「「racing」を作りました（難易度 normal）。ブラウザで
開けばそのまま遊べます。」

Four directions:

  (a) an English request is answered in English, with no Japanese script
      anywhere except the operator's own title - a name they gave, quoted
      back as they wrote it (C-1929's judge failed its own subject on this
      before it was corrected);
  (b) a Japanese request's reply is unchanged, character for character,
      against wording written out here;
  (c) the table reaches every branch of the reply, not just the happy one:
      a buildable genre, a genre that cannot be built, and a subject the
      page does not draw. Translating the success and stopping is the
      commonest half-job, and it is invisible to a table of successes;
  (d) and the list of what CAN be built, in an English reply, is made of
      words the detector actually accepts. That list exists to tell a
      reader what to ask for. A list they cannot read is useless, and a
      list of English words the router does not answer to is worse - it
      invites a request that will not work. Each name is fed back in as
      「make a <name> game」 and must route to the template it was listed
      for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(
    r"[぀-ゟ゠-ヿ一-鿿々ー、。「」（）・]"
)

#: (English request, Japanese request, the branch it exercises, wording the
#: Japanese reply must still contain).
CASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "make a racing game",
        "レースゲームを作って",
        "built",
        "を作りました（難易度 normal）。ブラウザで開けばそのまま遊べます。",
    ),
    (
        "make a fighting game",
        "格闘ゲームを作って",
        "unbuildable-genre",
        "型はまだ作れないため、代わりに既定の",
    ),
    (
        "make a game about a cat",
        "猫のゲームを作って",
        "undepicted-subject",
        "の題材を描く型はまだ無いため、代わりに既定の",
    ),
)


@dataclass(frozen=True)
class GameLanguageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _make(message: str) -> tuple[str, str]:
    """The reply, and the title of the game it is about."""

    from sidra_ai.creation.game_job import build_game_generator
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.evals.scratch import scratch_dir

    generate = build_game_generator(scratch_dir("sidra-game-language-"))
    outcome = generate(message, detect_creation_intent(message))
    title = ""
    quoted = re.search(r"[“「]([^”」]{1,40})[”」]", outcome.summary)
    if quoted:
        title = quoted.group(1)
    return outcome.summary, title


def evaluate_game_reply_matches_the_language_asked() -> GameLanguageResult:
    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # (c) every branch, checked before the cases are read
    branches = {branch for _en, _ja, branch, _want in CASES}
    if branches != {"built", "unbuildable-genre", "undepicted-subject"}:
        failures.append(
            f"the cases reach only {sorted(branches)} - a table of successes "
            "cannot see a reply that was translated only where it succeeds"
        )
    else:
        checks += 1

    for english, japanese, branch, expected_ja in CASES:
        reply_en, title_en = _make(english)
        reply_ja, _ = _make(japanese)

        # (a) English in, English out - minus the operator's own title
        stray = _JAPANESE.findall(reply_en.replace(title_en, "") if title_en else reply_en)
        if stray:
            failures.append(
                f"{branch}「{english}」 was answered with Japanese in it "
                f"({''.join(sorted(set(stray))[:8])}): {reply_en[:80]}"
            )
        else:
            checks += 1

        # (b) the Japanese reply is what it always was
        if expected_ja not in reply_ja:
            failures.append(
                f"{branch}「{japanese}」 now reads 「{reply_ja[:70]}」 - it must "
                f"still contain 「{expected_ja}」"
            )
        else:
            checks += 1
        readings.append(f"{branch}「{english}」→「{reply_en[:44]}」")

    # (d) the English list names things the router answers to
    from sidra_ai.creation.games import TEMPLATES, detect_genre
    from sidra_ai.creation.vocabulary import english_label_for

    unroutable: list[str] = []
    for template in TEMPLATES:
        name = english_label_for(template)
        if _JAPANESE.search(name):
            unroutable.append(f"{template}: 「{name}」 is not an English name")
            continue
        routed = detect_genre(f"make a {name} game")
        if routed is None or routed.template != template:
            got = "nothing" if routed is None else routed.template
            unroutable.append(f"{template}: 「make a {name} game」 routes to {got}")
    if unroutable:
        failures.append(
            "the English list names things the router does not answer to: "
            + "; ".join(unroutable[:3])
        )
    else:
        checks += 1

    return GameLanguageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
