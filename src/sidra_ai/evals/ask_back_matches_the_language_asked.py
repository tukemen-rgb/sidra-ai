"""Do the three ask-backs answer in the language they were asked in?

C-1537, filed by the outside critic after counting fourteen faces of an
English request and finding eleven already English. The three that were not
are the ask-backs: ``ambiguous`` (a bare artifact name - 「racing game」),
``unnamed`` (a request that names nothing - 「surprise me」) and ``empty``
(nothing, whitespace, or symbols only).

The filing read the three as one defect. Measured against the real
``SidraService``, they are not:

* **ambiguous and unnamed were genuinely wrong.** English in, Japanese back,
  from a product that answers the same person in English everywhere else -
  the help branch (C-1904), the how-to branch (C-1921), the unsupported-kind
  decline (C-1919) and every creation summary. The ask-backs were added later
  (C-1515 / C-1527 / C-1530) than rule 6 was taught, so they never got it.
* **empty was already right, and for a stated reason.** There is no language
  in an empty message to match, and ``_reply_in_japanese`` answers a message
  with no language at all in Japanese on purpose: this product's readers are
  Japanese, and the English branch would hand them 「Run POST
  /v1/github/analyze」 (C-1248). So the honest target is 11 -> 13 of fourteen
  faces, not 11 -> 14.

That third face is counted here rather than dropped. Dropping it would leave
the product's one deliberate Japanese-by-default reply unguarded, and the
next pass at "make the ask-backs English" would take it - undoing C-1248 in
the name of finishing C-1537. Scoring it pins it.

**What this counts.** One point per ask-back kind whose reply is in the
language the rule names, with the Japanese side as a GUARD rather than half
the score (C-1939): if a Japanese request stops getting a Japanese ask-back,
the whole number is 0, because an English reply bought by breaking the
Japanese one is not progress.

Read off the real service (C-1640), not off the source: each case calls
``SidraService.chat`` and reads the answer it returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_LATIN = re.compile(r"[A-Za-z]")

#: An English ask that lands on each branch, and its Japanese twin. The
#: ambiguous pair is a bare artifact name; the unnamed pair asks for a thing
#: without naming one. The empty pair has no language on either side - that is
#: the point of it.
ENGLISH_AMBIGUOUS = "racing game"
JAPANESE_AMBIGUOUS = "パズル"
ENGLISH_UNNAMED = "surprise me"
JAPANESE_UNNAMED = "なにか作って"
NO_LANGUAGE = ("", "   ", "...")


@dataclass(frozen=True)
class AskBackLanguageResult:
    sides_right: int
    sides_total: int = 3
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _english_enough(text: str) -> bool:
    """English prose: Latin letters and no Japanese script.

    Same one-sided test as ``vocabulary.is_english_text``. The operator's own
    subject is quoted back inside the sentence, so a Japanese subject in an
    English frame would fail this - which is why the ambiguous case quotes an
    English subject and the Japanese case is checked for its own words rather
    than for the absence of Latin.
    """
    return bool(_LATIN.search(text)) and not _JAPANESE.search(text)


def _kinds_named(answer: str) -> int:
    """How many makeable kinds the sentence itself names, in English.

    Read from the service's own English label table, so a generator added or
    removed in the router changes this count with no edit here - the same
    reason ``_KIND_LABELS_EN`` exists beside ``_KIND_LABELS`` (C-1919).
    """
    from sidra_ai.api.service import _KIND_LABELS_EN

    lowered = answer.lower()
    return sum(1 for label in _KIND_LABELS_EN.values() if label.lower() in lowered)


def evaluate_ask_back_matches_the_language_asked() -> AskBackLanguageResult:
    from sidra_ai.api.service import SidraService

    service = SidraService()
    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    def ask(message: str) -> dict:
        return service.chat(message)

    # --- 1. ambiguous ----------------------------------------------------
    english = ask(ENGLISH_AMBIGUOUS)
    problems: list[str] = []
    if english.get("refusal") != "ambiguous":
        problems.append(f"landed on {english.get('refusal')!r}, not the ambiguous branch")
    answer = english.get("answer", "")
    if not _english_enough(answer):
        problems.append("the ask-back is not in English")
    if ENGLISH_AMBIGUOUS not in answer:
        # Asking "which did you mean" without repeating what was said makes
        # the reader supply the subject from memory - the ask-back's whole job
        # is to hand it back (C-1527).
        problems.append("the subject the operator typed is not quoted back")
    if "repositor" not in answer.lower():
        problems.append("the search half of the choice is gone")
    if _kinds_named(answer) < 2:
        problems.append(f"only {_kinds_named(answer)} kinds named in the reply itself")
    readings.append(f"ambiguous EN={answer[:48]!r}")
    if problems:
        failures.append("ambiguous: " + "; ".join(problems))
    else:
        right += 1

    # --- 2. unnamed ------------------------------------------------------
    english = ask(ENGLISH_UNNAMED)
    problems = []
    if english.get("refusal") != "unnamed":
        problems.append(f"landed on {english.get('refusal')!r}, not the unnamed branch")
    answer = english.get("answer", "")
    if not _english_enough(answer):
        problems.append("the ask-back is not in English")
    if "make" not in answer.lower():
        problems.append("the reply no longer says what it can make")
    # The list is what turns a dead end into a choice (C-1530). An English
    # sentence that dropped it would pass rule 6 while saying less than the
    # Japanese one - translation by deletion, the escape C-1941 closed.
    #
    # Counted **in the sentence**, not in the metadata. The first version of
    # this check read `creation.outcome.offered`, which carries the Japanese
    # labels and is built before the sentence is - so a probe that deleted the
    # whole English list still scored 3/3. A check that cannot fail is not a
    # check; this one is what caught that.
    if _kinds_named(answer) < 2:
        problems.append(f"only {_kinds_named(answer)} kinds named in the reply itself")
    readings.append(f"unnamed EN={answer[:48]!r}")
    if problems:
        failures.append("unnamed: " + "; ".join(problems))
    else:
        right += 1

    # --- 3. empty: no language in, this product's language out -----------
    problems = []
    for message in NO_LANGUAGE:
        reply = ask(message)
        if reply.get("refusal") != "empty":
            problems.append(f"{message!r} landed on {reply.get('refusal')!r}")
            continue
        if not _JAPANESE.search(reply.get("answer", "")):
            problems.append(f"{message!r} was answered in something else")
    readings.append(f"no-language n={len(NO_LANGUAGE)}")
    if problems:
        failures.append("empty: " + "; ".join(problems))
    else:
        right += 1

    # --- guard: the Japanese side of the two that changed ----------------
    guard: list[str] = []
    japanese = ask(JAPANESE_AMBIGUOUS)
    if japanese.get("refusal") != "ambiguous":
        guard.append("the Japanese ambiguous ask stopped reaching its branch")
    elif "リポジトリから探しますか" not in japanese.get("answer", ""):
        guard.append("the Japanese ambiguous ask-back lost its own words")
    japanese = ask(JAPANESE_UNNAMED)
    if japanese.get("refusal") != "unnamed":
        guard.append("the Japanese unnamed ask stopped reaching its branch")
    elif "何をお作りしましょうか" not in japanese.get("answer", ""):
        guard.append("the Japanese unnamed ask-back lost its own words")
    if guard:
        japanese_held = False
        failures.append("Japanese: " + "; ".join(guard))

    return AskBackLanguageResult(
        sides_right=right if japanese_held else 0,
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = [
    "AskBackLanguageResult",
    "evaluate_ask_back_matches_the_language_asked",
]
