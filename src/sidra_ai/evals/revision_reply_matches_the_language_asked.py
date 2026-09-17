"""When a revision is asked in English, is it answered in English?

The product already has the rule and writes it down: `_reply_in_japanese`
in `models/echo.py` is 「SYSTEM_PROMPT rule 6, the language a reply takes」
- Japanese script or punctuation means Japanese, an input with no language
at all (digits, symbols) means Japanese, and English is reserved for a
request actually written in a Latin script. The Q&A lane follows it
(`answer_language_matches_question`).

The creation lane did not, and C-1928 is what made that reachable: before
it, an English revision was not understood at all, so there was no reply
to get wrong. Afterwards an operator could say 「make it harder」, have it
done, and be told 「「冒険」を修正しました: 難易度 normal→hard。」

Both directions, and the second is the heavier one:

  (a) an English request is answered in English - no Japanese script
      anywhere in the reply **except the game's own title**, which is a
      name the operator gave and is quoted back as they wrote it. The
      first version of this judge failed its own subject on 「冒険」 and
      was wrong to: translating somebody's title would be a different
      defect, not a fix;
  (b) a Japanese request's reply is **unchanged, character for character**,
      against wording written out here. Existing readers are the ones with
      something to lose, and "we added English" is the commonest way to
      move a sentence nobody asked to move.

Driven through the real reviser against a real saved game, not by reading
the source (C-1640): the reply is built from the change list, and a frame
translated without its contents is a half-English sentence.

Refusals are in the table as well as confirmations. A product that answers
a success in English and a refusal in Japanese has told the operator it
can speak their language and then declined to, at exactly the moment it is
also declining to do what they asked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿々ー、。「」]")

#: (English request, Japanese request, what must appear in the Japanese
#: reply). The Japanese column is quoted here so a change to it is a
#: failure rather than a silent rewording.
PAIRS: tuple[tuple[str, str, str], ...] = (
    (
        "make it harder",
        "さっきのゲームをもっと難しくして",
        "を修正しました: 難易度 normal→hard。旧版のファイルもそのまま残っています。",
    ),
    (
        "make it blue",
        "それを青くして",
        "を修正しました: 差し色。旧版のファイルもそのまま残っています。",
    ),
    (
        "undo that",
        "さっきのゲームを元に戻して",
        "はまだ一度も修正していないので、戻せる前の版がありません。",
    ),
)

#: The English request that reaches the undo *confirmation* rather than its
#: refusal - it needs a change to undo, so the driver makes one first.
UNDO_AFTER_CHANGE = ("make it harder", "undo that")


@dataclass(frozen=True)
class RevisionLanguageResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _drive(sentence: str, *, first: str | None = None) -> tuple[str, str]:
    """The reply, and the title of the game it is about.

    The title comes back too because it is the one piece of Japanese that
    may legitimately appear in an English reply.
    """

    from sidra_ai.creation.games import generate_game, save_game
    from sidra_ai.creation.revise import (
        build_game_reviser,
        detect_revision_intent,
        save_meta,
    )
    from sidra_ai.evals.scratch import scratch_dir

    home = scratch_dir("sidra-revision-language-")
    built = generate_game("冒険ゲームを作って", template="adventure")
    page = save_game(built, home)
    save_meta(
        page,
        request="冒険ゲームを作って",
        template="adventure",
        difficulty=built.difficulty,
        theme="",
        title=built.title,
        panel={},
    )
    reviser = build_game_reviser(home)
    if first is not None:
        reviser(first, detect_revision_intent(first))
    intent = detect_revision_intent(sentence)
    if not intent.is_revision:
        return f"(not read as a revision: {intent.adjustments})", built.title
    return reviser(sentence, intent).summary, built.title


def evaluate_revision_reply_matches_the_language_asked() -> RevisionLanguageResult:
    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # The table has to hold a refusal as well as confirmations, or "answers
    # in English" is only proven for the happy path - which is the half a
    # product is most likely to translate and stop.
    if not any("ありません" in expected for _en, _ja, expected in PAIRS):
        failures.append(
            "the pairs contain no refusal - a reply that is English when it "
            "succeeds and Japanese when it declines is the shape this guards"
        )
    else:
        checks += 1

    for english, japanese, expected_ja in PAIRS:
        reply_en, title = _drive(english)
        reply_ja, _ = _drive(japanese)

        # (a) English in, English out - with the operator's own title taken
        # out first, because quoting it back is right.
        stray = _JAPANESE.findall(reply_en.replace(title, ""))
        if stray:
            failures.append(
                f"「{english}」 was answered with Japanese in it "
                f"({''.join(sorted(set(stray))[:6])}): {reply_en[:70]}"
            )
        else:
            checks += 1

        # ...and it actually said something
        if not reply_en.strip() or reply_en.startswith("(not read"):
            failures.append(f"「{english}」 produced no reply: {reply_en}")
        else:
            checks += 1

        # (b) the Japanese reply is what it always was
        if expected_ja not in reply_ja:
            failures.append(
                f"「{japanese}」 now reads 「{reply_ja[:80]}」 - it must still "
                f"contain 「{expected_ja}」"
            )
        else:
            checks += 1
        readings.append(f"「{english}」→「{reply_en[:48]}」")

    # the undo confirmation, which needs something to undo first
    first, then = UNDO_AFTER_CHANGE
    undo_reply, undo_title = _drive(then, first=first)
    stray = _JAPANESE.findall(undo_reply.replace(undo_title, ""))
    if stray:
        failures.append(
            f"the undo confirmation kept Japanese ({''.join(sorted(set(stray))[:6])}): "
            f"{undo_reply[:70]}"
        )
    else:
        checks += 1
    readings.append(f"undo →「{undo_reply[:48]}」")

    return RevisionLanguageResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
