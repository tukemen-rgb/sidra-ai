"""Is the record beside a single artifact in the language that was asked?

C-1947. ``records`` exists so that 「この game.html はいつ・何から作られたか」
has an answer a week later. C-1940 put the *production* log into the language
of the request; this one - the log for an artifact made on its own - was left
in Japanese, and this one is the common path. Six generators reach it through
``router._record``; the scaffolder reaches the other one. Somebody who writes
「make a gif of an owl」 gets the gif and, in the same directory, a file that
opens 「# 生成の記録」.

**What this counts.** Creation kinds whose standalone record comes out in the
language the request was written in - out of every kind the product has,
taken from ``CreationKind`` rather than from a list here (C-1938: a
hand-written list of kinds is how PROJECT went unmeasured for six items).

Three rules, the same ones the production set is held to (C-1941):

1. No Japanese at all in the log written for an English request.
2. The file is still a log - it has its records heading and at least one
   record line under it. A file that stopped being written is not "in
   English".
3. The Japanese side is a GUARD, not part of the count: ask in Japanese and
   the log must still be Japanese. If it is not, the count is zero.

**A kind that cannot be asked for in English fails, and says why.** It is
not skipped and it is not left out of the denominator - measured while this
was being written, ``art`` and ``project`` are unreachable in English:
「draw a picture of an owl」, 「draw an owl」, 「paint an owl」 and three more
phrasings all return ``CreationKind.UNKNOWN`` or route to ``GAME``. A judge
that quietly dropped them would report a full marks for a product two of
whose seven lanes an English speaker cannot enter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Japanese script. Punctuation is left out: a log may quote a title, and a
#: title is the operator's own word (C-1929).
_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: One request per kind, in each language. The kinds themselves come from the
#: enum; this is only how each one is asked for.
ASKS: dict[str, tuple[str, str]] = {
    "game": ("make a game about an owl", "ふくろうのゲームを作って"),
    "gif": ("make a gif of an owl", "ふくろうの GIF を作って"),
    "model3d": ("make a 3d model of an owl", "ふくろうの 3D モデルを作って"),
    "deck": ("make a slide deck about owls", "ふくろうのスライドを作って"),
    # 「資料」 reads as a deck, so the document lane is asked for with the
    # word that reaches it - checked, not assumed.
    "document": ("write a document about owls", "ふくろうについての文書を作って"),
    "art": ("draw a picture of an owl", "ふくろうの絵を描いて"),
    "project": ("make a game project about an owl", "ふくろうのゲームを企画から作って"),
}


@dataclass(frozen=True)
class StandaloneRecordResult:
    kinds_in_the_right_language: int
    kinds_total: int
    japanese_held: bool = True
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _log_for(request: str, expected_kind: str) -> tuple[str | None, str]:
    """The standalone log a request leaves behind, or why there is none."""

    from pathlib import Path

    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.creation.records import STANDALONE_LOG_NAME
    from sidra_ai.creation.router import build_default_router
    from sidra_ai.evals.scratch import scratch_dir

    directory = scratch_dir("sidra-standalone-record-")
    intent = detect_creation_intent(request)
    if intent.kind.value != expected_kind:
        return None, (
            f"「{request}」 is read as {intent.kind.value}, not {expected_kind}"
            " - this lane cannot be asked for in this language at all"
        )
    router = build_default_router(data_dir=str(directory))
    outcome = router.route(request, intent)
    if not outcome.handled:
        return None, f"「{request}」 was not handled"
    log = Path(directory) / STANDALONE_LOG_NAME
    if not log.is_file():
        return None, f"「{request}」 left no {STANDALONE_LOG_NAME}"
    return log.read_text(encoding="utf-8"), ""


def evaluate_standalone_record_matches_the_language_asked() -> StandaloneRecordResult:
    from sidra_ai.creation.intent import CreationKind
    from sidra_ai.creation.records import RECORDS_HEADING, RECORDS_HEADING_EN

    failures: list[str] = []
    readings: list[str] = []
    right = 0
    japanese_held = True

    kinds = sorted(
        kind.value for kind in CreationKind if kind is not CreationKind.UNKNOWN
    )
    missing_asks = sorted(set(kinds) - set(ASKS))
    if missing_asks:
        # Derived from the enum, so a kind added later is a loud gap rather
        # than one that is quietly never measured (C-1938).
        failures.append(f"no request is written for: {missing_asks}")

    for kind in kinds:
        if kind not in ASKS:
            continue
        english_ask, japanese_ask = ASKS[kind]

        english, why = _log_for(english_ask, kind)
        if english is None:
            failures.append(f"{kind}: {why}")
            readings.append(f"EN {kind} unreachable")
        else:
            left = [line for line in english.splitlines() if _JAPANESE.search(line)]
            is_log = RECORDS_HEADING_EN in english and "| made: " in english
            readings.append(f"EN {kind} ja-lines={len(left)}")
            if left:
                failures.append(
                    f"{kind}: {len(left)} lines of its English record are Japanese"
                )
            elif not is_log:
                failures.append(f"{kind}: the English record is not a record")
            else:
                right += 1

        japanese, why = _log_for(japanese_ask, kind)
        if japanese is None:
            japanese_held = False
            failures.append(f"{kind} (ja): {why}")
        else:
            if RECORDS_HEADING not in japanese or "| 作った物: " not in japanese:
                japanese_held = False
                failures.append(
                    f"{kind}: the Japanese record has moved - "
                    "the side that already worked"
                )
            readings.append(
                f"JA {kind} ja-lines="
                f"{len([l for l in japanese.splitlines() if _JAPANESE.search(l)])}"
            )

    return StandaloneRecordResult(
        # Zero when the Japanese side moved, so a gain on one side can never
        # pay for a loss on the other (C-1939).
        kinds_in_the_right_language=right if japanese_held else 0,
        kinds_total=len(kinds),
        japanese_held=japanese_held,
        failures=tuple(failures),
        readings=tuple(readings),
    )


__all__ = [
    "ASKS",
    "StandaloneRecordResult",
    "evaluate_standalone_record_matches_the_language_asked",
]
