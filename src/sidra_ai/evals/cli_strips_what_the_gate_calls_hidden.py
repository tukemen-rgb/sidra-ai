"""Does the terminal renderer remove every character the gate calls hidden?

C-1539, from the outside critic's fifteenth review.

``ask_cli`` states the promise itself: "Everything printed here derives from
repository content, which is DATA from outside. ... They are removed before
printing, and the removal is reported rather than done silently." Its comment
names the reason the CLI cannot simply defer to the gate: *"security/
detectors.py flags these on the way in; this removes them on the way out,
because the gate can be widened and a terminal cannot."*

The two lists disagreed. ``PromptInjectionDetector`` flags U+2060-U+2064 -
word joiner and the invisible math operators - as "zero-width/bidi control
characters used to hide payloads", and ``_STRIPPED_CODEPOINTS`` did not carry
them. So a character this project already calls hostile reached the terminal
in the answer, the citation reference, the excerpt and the source URL, and
``--json``'s warning (which counts against the same set) said nothing - the
one case the promise above rules out, since it is neither removed nor
reported.

The relation that has to hold is one-directional: **the terminal's set is a
superset of the gate's.** The CLI strips the four bidi isolates U+2066-U+2069
that the gate does not flag, and that is correct - it is the stricter side.

**What this counts.** One point per codepoint the gate flags, scored on all
three faces at once: gone from every printed field, reported on the way out,
and warned about in ``--json``. The required set is read out of
``_INVISIBLE_CHARS`` itself rather than copied, so widening the gate lowers
this number until the terminal follows - which is the drift that produced the
defect.

**Guards, not half the score** (C-1939):

* the four isolates the CLI strips beyond the gate must stay stripped, and
* ordinary text - Japanese, Latin, a url - must come through unchanged.

Otherwise the cheapest way to score 16 is to delete every character that is
not ASCII, which passes the count and destroys the product.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

#: The CLI is stricter than the gate here, and stays that way.
ISOLATES = (0x2066, 0x2067, 0x2068, 0x2069)

#: Ordinary content that must survive rendering untouched.
INNOCENT = "認証は OAuth2 を使う (see docs/AUTH.md)"


@dataclass(frozen=True)
class HiddenCharResult:
    codepoints_right: int
    codepoints_total: int
    guards_held: bool = True
    failures: tuple[str, ...] = ()


def gate_hidden_codepoints() -> tuple[int, ...]:
    """Every codepoint the ingestion gate calls a hiding character.

    Read off ``_INVISIBLE_CHARS`` by trying characters against it, not by
    re-typing its ranges - a second copy of the list is how the first two
    drifted apart.
    """
    from sidra_ai.security.detectors import _INVISIBLE_CHARS

    found = [cp for cp in range(0x0, 0x10000) if _INVISIBLE_CHARS.search(chr(cp))]
    found += [cp for cp in range(0xE0000, 0xE0080) if _INVISIBLE_CHARS.search(chr(cp))]
    return tuple(found)


def _render(payload: dict) -> tuple[str, str]:
    """What ``render`` printed, and what it said about it.

    The page and the note go to different streams - the rendered answer to
    stdout, 「取り除いて表示した」 to stderr - so a check that reads only one
    of them either misses the character or misses the report.
    """
    from sidra_ai.api import ask_cli

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        ask_cli.render(payload, base_url="http://127.0.0.1:8787")
    return out.getvalue(), err.getvalue()


def _json_warning(character: str) -> str:
    """What ``--json`` says on stderr about a payload carrying this character."""
    import httpx

    from sidra_ai.api import ask_cli

    body = {"answer": f"sidra{character}-ai", "citations": [], "refused": False}
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    )
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        ask_cli.main(["q", "--json"], client=client)
    return err.getvalue()


def evaluate_cli_strips_what_the_gate_calls_hidden() -> HiddenCharResult:
    required = gate_hidden_codepoints()
    failures: list[str] = []
    right = 0

    for codepoint in required:
        character = chr(codepoint)
        # All four printed faces at once: the answer, the citation reference,
        # the excerpt and the source url. A fix that scrubs only the answer
        # leaves the reference - the field that names which repository the
        # claim came from - spoofable.
        printed, reported = _render(
            {
                "answer": f"sidra{character}-ai は OAuth を使う。",
                "citations": [
                    {
                        "label": "1",
                        "citation": f"tukemen-rgb/sidra{character}-ai docs/AUTH.md",
                        "excerpt": f"OAuth{character} を使う",
                        "url": f"https://example.com/a{character}b",
                        "trust_level": "internal_repo",
                    }
                ],
            }
        )
        problems: list[str] = []
        if character in printed:
            problems.append(f"survives in {printed.count(character)} printed field(s)")
        elif "取り除いて表示した" not in reported:
            # Removed, but silently - the half of the promise that says a
            # reader is told what happened to the text they are reading.
            problems.append("removed without saying so")
        if "端末制御文字" not in _json_warning(character):
            problems.append("--json does not warn")
        if problems:
            failures.append(f"U+{codepoint:04X}: " + "; ".join(problems))
        else:
            right += 1

    guards_held = True
    for codepoint in ISOLATES:
        character = chr(codepoint)
        if character in _render({"answer": f"a{character}b", "citations": []})[0]:
            guards_held = False
            failures.append(f"guard: U+{codepoint:04X} stopped being stripped")
    innocent, _ = _render({"answer": INNOCENT, "citations": []})
    if INNOCENT not in innocent:
        guards_held = False
        failures.append("guard: ordinary text no longer survives rendering")

    return HiddenCharResult(
        codepoints_right=right if guards_held else 0,
        codepoints_total=len(required),
        guards_held=guards_held,
        failures=tuple(failures),
    )


__all__ = [
    "HiddenCharResult",
    "evaluate_cli_strips_what_the_gate_calls_hidden",
    "gate_hidden_codepoints",
]
