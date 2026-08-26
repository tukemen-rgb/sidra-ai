"""What a generator is allowed to build content from.

A ``Fact`` is one retrieved passage plus where it came from. It lives here,
apart from any particular generator, because the router now carries evidence
to whichever generator it calls, and a router that had to import the deck
builder to know what a fact is would depend on every generator that ever
exists.

The type is deliberately thin: text and a source label, both already screened
by the security gate on the way into the index. There is no score, no chunk
id and no document object, because a generator that could see those would be
able to reach back into retrieval, and its output is supposed to be bounded
by exactly what it was handed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Anything that looks like a quantity. Deliberately broad - a false positive
#: costs one extra evidence check, a false negative puts an unsourced number
#: in front of a reader, which is the failure this whole path exists to
#: prevent.
NUMBER = re.compile(r"\d[\d,.\s]*\s*(?:%|％|円|万|億|人|件|倍|pt|x)?", re.IGNORECASE)


@dataclass(frozen=True)
class Fact:
    """One retrieved claim and where it came from.

    ``source`` is a repository-and-path label. ``text`` is passage text the
    caller has already taken from an allowed chunk - a generator never reads
    a document itself.
    """

    text: str
    source: str

    def mentions_number(self) -> bool:
        return bool(NUMBER.search(self.text))


__all__ = ["Fact", "NUMBER"]
