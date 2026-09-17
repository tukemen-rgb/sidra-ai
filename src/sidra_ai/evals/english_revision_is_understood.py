"""Is a revision asked in English understood the way the Japanese one is?

§9 records the market's second-biggest complaint about AI game tools as
weak intent understanding plus fixes with side effects, and names
生成後の対話的修正 as the first thing SIDRA has not won. The side-effect
half is watched by `revision_changes_only_what_it_owns` (C-1894). This is
the understanding half, and it was measured in one language only.

Measured before C-1928: Japanese revisions were read **6 of 6** and
English ones **0 of 7**. 「make it harder」 came back with no adjustment at
all - and was then picked up as a *weak creation* intent, so an operator
asking to change their own game was asked what they would like made;
「undo that」 was not even that, and fell through to the corpus search.

The tables were Japanese-only. English was not being refused, it was
matching nothing.

What this checks, in four directions, because the first one alone is
satisfied by a detector that calls everything a revision:

  (a) each English request is read as the SAME adjustment as its Japanese
      twin - paired in one table, so neither language can drift alone -
      **and is actually acted on**. Reading the adjustment is not enough:
      every English form here carries a back-reference (「it」, 「the game」),
      so the detector has a target and must return a revision rather than
      stopping to ask which artifact. Sabotage D1 removed the English
      back-reference entirely and the first version of this judge stayed
      green, because it compared only the adjustment dictionary - a
      detector that understood the words and refused to act would have
      passed;
  (b) an English *creation* request is not stolen - 「make a harder game」
      belongs to the creation detector exactly as 「難しいゲームを作って」
      does, and the boundary between it and 「make it harder」 is the whole
      point;
  (c) the Japanese side still reads exactly what it read before, because a
      fix to the language that was broken must not move the one that
      worked;
  (d) and an English keyword sitting inside a longer word changes nothing.
      「title」 contains 「it」 and 「shredder」 contains 「red」; C-1913 and
      C-1916 were both this same defect in the title stripper, so it is
      asked here before it happens rather than after.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (Japanese, English, the adjustment both must be read as). One row, both
#: languages, so a change that moves one and not the other cannot pass.
PAIRS: tuple[tuple[str, str, dict], ...] = (
    ("もっと難しくして", "make it harder", {"difficulty": "+1"}),
    ("もっと簡単にして", "make it easier", {"difficulty": "-1"}),
    ("速くして", "make it faster", {"difficulty": "+1"}),
    ("遅くして", "make it slower", {"difficulty": "-1"}),
    ("色を青くして", "make it blue", {"accent": "#4aa8ff"}),
    ("色を赤くして", "turn it red", {"accent": "#ff5a5a"}),
    ("元に戻して", "undo that", {"revert": "1"}),
    ("難易度を normal にして", "set it to normal", {"difficulty": "=normal"}),
)

#: English requests that must stay with the creation detector.
CREATION_ENGLISH: tuple[str, ...] = (
    "make a harder game",
    "make an easier puzzle game",
    "make a racing game",
    "make a blue game",
    "make art of the sea",
    # The row sabotage D3 needed. A stray back-reference does no harm on its
    # own - without an adjustment the message is still not a change - so a
    # substring-matched 「it」 only bites when it turns OFF the creation veto
    # on a request that also carries an adjustment word. 「title」 contains
    # 「it」, and with substring matching this creation request was read as
    # 「make the existing game harder」. Without this row the sabotage went
    # green (the same hole C-1896 D4 and C-1920 D3 each had: the table has
    # to hold the case that breaks).
    "make a harder game with a title screen",
)

#: ASCII words with Japanese glued to either side, and what they must still
#: be read as. This is the product's OWN printed advice - it tells operators
#: to type 「さっきのゲームの難易度をeasyにして」 - and C-1928's first attempt
#: refused all three rungs, because `\b` needs a non-word character beside
#: the word and kana and kanji are word characters. Caught by
#: `test_printed_advice_actually_works` rather than by this judge, so the
#: case is brought in here: the advice a product prints is the first thing
#: its own language rules have to survive.
GLUED_TO_JAPANESE: tuple[tuple[str, dict], ...] = (
    ("さっきのゲームの難易度をeasyにして", {"difficulty": "=easy"}),
    ("さっきのゲームの難易度をnormalにして", {"difficulty": "=normal"}),
    ("さっきのゲームの難易度をhardにして", {"difficulty": "=hard"}),
)

#: Longer words that merely contain an English keyword. None of these asks
#: for anything, so none may be read as a change.
SUBSTRING_TRAPS: tuple[str, ...] = (
    "what does the title mean",
    "the shredder level",
    "whitespace in the panel",
    "explain the editor",
)


@dataclass(frozen=True)
class EnglishRevisionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def evaluate_english_revision_is_understood() -> EnglishRevisionResult:
    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.revise import detect_revision_intent

    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # The table must carry more than one kind of adjustment, or a detector
    # that only learned the word 「harder」 would look complete.
    kinds = {key for _ja, _en, want in PAIRS for key in want}
    if len(kinds) < 3:
        failures.append(
            f"the pairs cover only {sorted(kinds)} - one kind of adjustment is "
            "not evidence that revisions are understood"
        )
    else:
        checks += 1

    for japanese, english, want in PAIRS:
        ja = detect_revision_intent(japanese).adjustments
        en = detect_revision_intent(english).adjustments

        # (c) the language that worked still works, and reads what it read
        if ja != want:
            failures.append(f"「{japanese}」 now reads {ja or '{}'}, wanted {want}")
        else:
            checks += 1

        # (a) and the English twin reads the same thing...
        english_intent = detect_revision_intent(english)
        if english_intent.adjustments != want:
            failures.append(
                f"「{english}」 reads {english_intent.adjustments or '{}'}, wanted "
                f"{want} - its Japanese twin 「{japanese}」 reads {ja or '{}'}"
            )
        else:
            checks += 1

        # ...and is acted on, because it points at something
        if not english_intent.is_revision:
            failures.append(
                f"「{english}」 was understood ({english_intent.adjustments or '{}'}) "
                "but not acted on - it says 「it」, so the detector has its "
                "target and should not be asking which artifact"
            )
        else:
            checks += 1
        readings.append(f"「{english}」＝「{japanese}」→ {want}")

    # (b) creation requests are not stolen
    for request in CREATION_ENGLISH:
        revision = detect_revision_intent(request)
        if revision.is_revision or revision.adjustments:
            failures.append(
                f"「{request}」 was read as a change ({revision.adjustments}) - it "
                "is a request to make something, not to change something"
            )
        elif not detect_creation_intent(request).is_creation:
            failures.append(
                f"「{request}」 is neither a revision nor a creation - it fell "
                "through both detectors"
            )
        else:
            checks += 1

    # ...and the same boundary rule, from the other side: an ASCII word with
    # Japanese glued to it is still that word.
    for glued, want in GLUED_TO_JAPANESE:
        got = detect_revision_intent(glued).adjustments
        if got != want:
            failures.append(
                f"「{glued}」 reads {got or '{}'}, wanted {want} - this is the "
                "sentence the product's own advice tells operators to type"
            )
        else:
            checks += 1

    # (d) a keyword inside a longer word is not a keyword
    for trap in SUBSTRING_TRAPS:
        revision = detect_revision_intent(trap)
        if revision.is_revision or revision.adjustments:
            failures.append(
                f"「{trap}」 was read as a change ({revision.adjustments}) - an "
                "English keyword inside a longer word is not a keyword"
            )
        else:
            checks += 1

    return EnglishRevisionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
