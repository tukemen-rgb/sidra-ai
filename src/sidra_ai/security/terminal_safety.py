"""Strip terminal-hostile control characters from untrusted text before it is
printed to an operator's terminal.

Content that originated outside SIDRA - a quarantined document, a retrieved
chunk - can carry raw C0/C1 controls, DEL, bidi overrides, zero-width
characters or the BOM. Printed straight to a terminal those move the cursor,
recolour or retitle the window, clear the screen, or hide text, so a reviewer
sees something other than what is really there. They are removed before
display; tab and newline are kept because a terminal shows them harmlessly and
they carry real layout.

``ask_cli`` keeps its own copy of this set for the ask path (C-1627); this is
the security-layer home the review CLI uses (C-1647). The two encode the same
Unicode categories.
"""

from __future__ import annotations

#: Codepoints removed before untrusted text reaches a terminal: the C0 controls
#: except tab (0x09) and newline (0x0A), DEL (0x7F), the C1 controls
#: (0x80-0x9F, which include CSI 0x9B), the zero-width range (0x200B-0x200F),
#: the bidi embeddings/overrides (0x202A-0x202E), the bidi isolates
#: (0x2066-0x2069), and the BOM (0xFEFF).
STRIPPED_CODEPOINTS = frozenset(
    [code for code in range(0x00, 0x20) if code not in (0x09, 0x0A)]
    + [0x7F]
    + list(range(0x80, 0xA0))
    + list(range(0x200B, 0x2010))
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A))
    + [0xFEFF]
)


def scrub_for_terminal(text: str) -> tuple[str, int]:
    """Return ``(clean_text, removed_count)`` with terminal-hostile codepoints gone."""

    kept = [character for character in text if ord(character) not in STRIPPED_CODEPOINTS]
    return "".join(kept), len(text) - len(kept)


__all__ = ["STRIPPED_CODEPOINTS", "scrub_for_terminal"]
