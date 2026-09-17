"""When an English request names an amount or a format, is it heard?

The product is honest about amounts it cannot honour. 「30フレームのGIFを
作って」 is told 「依頼は 30 フレームでしたが…フレーム数は指定できません」
(C-1823); 「3つの3Dモデル」 is told the count is fixed (C-1832); 「5枚の
スライド」 is told the deck is four (C-1821).

None of that reached an English request, because all four parsers read
Japanese units only. Measured before C-1934: **English 0 of 11, Japanese
4 of 4**. 「make a 5 second gif」 was handed a 0.8 second loop and told
nothing at all - not a reply in the wrong language, a different artifact
than the one asked for, silently.

What this reads is the **reply the generator produces**, not the parser
(C-1640). A parser that returns a number while the caveat stays silent
would pass a parser-level check and change nothing for the operator.

Four directions:

  (a) an English request that names an amount gets the caveat;
  (b) its Japanese twin still gets it, in the same wording as before -
      the language that worked must not move;
  (c) a request that names NO amount gets no caveat. C-1823's own reason:
      a caveat that fires with nothing to report stops being read, and
      widening a pattern is exactly how false positives arrive;
  (d) and the shapes that must NOT be read as amounts are listed and
      checked: 「make a 3d model」 is not three of anything, and 「make a
      gif of the 90s」 is not ninety seconds. That second one is why the
      bare 「5s」 form was deliberately left out.

C-1937 added the fifth parser of the same family, the requested FORMAT.
Its words were already English - it was the lookbehind that was Japanese -
so 「write a report in Word」 named a format nobody read, C-1834's
disclosure never fired, and the deck answered by naming PowerPoint, a
format the operator had not asked for. Its rows sit in the same tables,
including the silent side: 「a report about Word」 is a subject, not a
format, exactly as 「Wordの使い方」 is on the Japanese side.
"""

from __future__ import annotations

from dataclasses import dataclass

#: (kind, English request, Japanese request, a phrase the caveat must carry
#: in each language).
AMOUNTS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "gif-frames",
        "make a 30 frame gif",
        "30フレームのGIFを作って",
        "The frame count cannot be set",
        "フレーム数は指定できません",
    ),
    (
        "gif-seconds",
        "make a 5 second gif",
        "5秒のGIFを作って",
        "The length cannot be set",
        "長さは指定できません",
    ),
    (
        "model-count",
        "make 3 models of an owl",
        "3つの3Dモデルを作って",
        "The count cannot be set",
        "個数は指定できません",
    ),
)

#: The deck says the same kind of thing. When C-1934 wrote this row the
#: deck's reply was still Japanese in both languages, so the phrase looked
#: for was 「枚数は指定できません」; C-1935 then translated that lane, which is
#: the change C-1934's own entry said would come. The amount being HEARD is
#: what this item measures, and it still is - only the language it is said
#: in moved, so the expectation moves with it rather than being dropped.
#: Both languages are listed, so the row keeps meaning what it meant.
DECK_CASE = (
    "make a 5 slide deck about an owl",
    "The slide count cannot be set",
)
DECK_CASE_JA = ("5枚のスライドを作って", "枚数は指定できません")

#: C-1937: the format, in both languages and on both surfaces that carry a
#: format notice. The deck row is the one that was actively misleading -
#: with the format unread it named PowerPoint, which nobody had asked for.
FORMAT_CASES: tuple[tuple[str, str, str], ...] = (
    ("document", "write a report about an owl in Word", "Word cannot be produced"),
    ("document", "レポートをWordで作って", "なお Word 形式では作れないため"),
    ("deck", "make a deck about an owl as pdf", "PDF cannot be produced"),
    ("deck", "スライドをPDFで作って", "なお PDF 形式では作れないため"),
)

#: Requests that name no amount. Nothing may be said about one.
NO_AMOUNT: tuple[tuple[str, str], ...] = (
    ("gif", "make a gif of an owl"),
    ("model3d", "make a model of an owl"),
    ("document", "write a report about an owl"),
)

#: Shapes that contain a digit but name no amount. Each must stay silent.
NOT_AMOUNTS: tuple[tuple[str, str], ...] = (
    ("model3d", "make a 3d model of an owl"),
    ("gif", "make a gif of the 90s"),
    # C-1937: a format named as the SUBJECT is not a format request.
    ("document", "write a report about Word"),
)

_BUILDERS = {
    "gif": ("sidra_ai.creation.gif_job", "build_gif_generator"),
    "model3d": ("sidra_ai.creation.model3d_job", "build_model3d_generator"),
    "deck": ("sidra_ai.creation.deck_job", "build_deck_generator"),
    "document": ("sidra_ai.creation.document_job", "build_document_generator"),
}

_KIND_OF = {
    "gif-frames": "gif",
    "gif-seconds": "gif",
    "model-count": "model3d",
}


@dataclass(frozen=True)
class EnglishAmountResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def _say(kind: str, request: str) -> str:
    import importlib

    from sidra_ai.creation.intent import detect_creation_intent
    from sidra_ai.evals.scratch import scratch_dir

    module, factory = _BUILDERS[kind]
    make = getattr(importlib.import_module(module), factory)(
        scratch_dir(f"sidra-amount-{kind}-")
    )
    return make(request, detect_creation_intent(request)).summary


#: Every caveat phrase, in both languages - used to prove SILENCE, which
#: needs the full set rather than the one phrase a row happens to expect.
_ALL_CAVEATS = (
    "cannot be set",
    "指定できません",
    # C-1937: the format notices count as "something was claimed about an
    # amount the operator named", so a request that names none must not
    # produce one of these either.
    "cannot be produced",
    "形式では作れないため",
)


def evaluate_english_amount_is_heard() -> EnglishAmountResult:
    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    # The table has to hold more than one unit, or "amounts are heard" is
    # proven for whichever single word someone happened to widen.
    units = {kind for kind, *_rest in AMOUNTS}
    if len(units) < 3:
        failures.append(
            f"the table covers only {sorted(units)} - one unit is not evidence "
            "that amounts are heard"
        )
    else:
        checks += 1

    for label, english, japanese, want_en, want_ja in AMOUNTS:
        kind = _KIND_OF[label]
        said_en = _say(kind, english)
        said_ja = _say(kind, japanese)

        if want_en not in said_en:
            failures.append(
                f"{label}「{english}」: no caveat - wanted 「{want_en}」 in: "
                f"...{said_en[-90:]}"
            )
        else:
            checks += 1

        if want_ja not in said_ja:
            failures.append(
                f"{label}「{japanese}」: the Japanese caveat stopped - wanted "
                f"「{want_ja}」 in: ...{said_ja[-70:]}"
            )
        else:
            checks += 1
        readings.append(f"{label}「{english}」→ 注記あり")

    # the deck, in both languages
    for deck_ask, deck_want in (DECK_CASE, DECK_CASE_JA):
        said_deck = _say("deck", deck_ask)
        if deck_want not in said_deck:
            failures.append(
                f"deck「{deck_ask}」: no caveat - wanted 「{deck_want}」 in: "
                f"...{said_deck[-90:]}"
            )
        else:
            checks += 1

    # ...and the silent table has to hold a format named as a SUBJECT.
    # Sabotage D5 deleted that row and dropped the in/as/to gate together,
    # and the sheet stayed clean: the row is what makes the gate's job
    # visible, so it cannot be removable without a word (the same hole
    # C-1896 D4, C-1920 D3 and C-1928 D3 each had).
    if not any("about Word" in request for _kind, request in NOT_AMOUNTS):
        failures.append(
            "the silent table holds no format named as a subject - without one, "
            "a gate that reads every 「Word」 as a format request passes"
        )
    else:
        checks += 1

    # C-1937: and the format table has to hold both languages on both
    # surfaces, or "the format is heard" is proven for whichever half
    # somebody happened to widen - which is exactly the state this item
    # found (the words were English already; the gate was not).
    format_pairs = {(kind, "en" if request.isascii() else "ja")
                    for kind, request, _want in FORMAT_CASES}
    if format_pairs != {("document", "en"), ("document", "ja"),
                        ("deck", "en"), ("deck", "ja")}:
        failures.append(
            f"the format rows cover {sorted(format_pairs)} - both languages on "
            "both surfaces that carry a format notice"
        )
    else:
        checks += 1

    # C-1937: the format, read from the reply the operator gets
    for kind, request, want in FORMAT_CASES:
        said = _say(kind, request)
        if want not in said:
            failures.append(
                f"{kind}「{request}」: the format was not heard - wanted "
                f"「{want}」 in: ...{said[-90:]}"
            )
        else:
            checks += 1
        readings.append(f"format「{request}」→ 注記あり")

    # (c) and (d): silence where there is nothing to report
    for kind, request in NO_AMOUNT + NOT_AMOUNTS:
        said = _say(kind, request)
        spoke = [mark for mark in _ALL_CAVEATS if mark in said]
        if spoke:
            failures.append(
                f"{kind}「{request}」 names no amount but was answered with a "
                f"caveat about one ({'、'.join(spoke)}): ...{said[-80:]}"
            )
        else:
            checks += 1

    return EnglishAmountResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
