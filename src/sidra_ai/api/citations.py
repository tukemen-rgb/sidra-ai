"""How a cited chunk becomes the excerpt an operator actually sees.

This is one function on purpose. Until now the rule - take the opening of the
chunk, screen it, keep it inside the cap - lived only inside the service, and
anything that wanted to *measure* the excerpt had to re-implement it. A
measurement that re-implements the thing it measures drifts from it silently
and then reports numbers about a program that does not exist, which is the
failure mode this project has already been bitten by once.

So the service calls this, and ``measure_outcomes.py`` calls this, and when
the selection rule changes both move together or neither does.
"""

from __future__ import annotations

from sidra_ai.api.schemas import MAX_CITATION_EXCERPT_CHARS
from sidra_ai.security.output_guard import OutputGuard


def citation_excerpt(content: str, output_guard: OutputGuard) -> tuple[str, bool]:
    """Return ``(excerpt, withheld)`` for one cited chunk.

    ``withheld`` is true when evidence exists but the output guard refused to
    show it. That is not the same fact as an empty excerpt and the caller has
    to be able to tell them apart: "we are not showing you this" and "there is
    nothing here" read identically once both are the empty string.

    The cap is applied twice - before and after screening - because the guard
    may redact in place and a redaction can be longer than what it replaced.
    """

    excerpt = content[:MAX_CITATION_EXCERPT_CHARS]
    if not excerpt:
        return "", False
    guarded = output_guard.scan(excerpt)
    if guarded.blocked:
        return "", True
    return guarded.content[:MAX_CITATION_EXCERPT_CHARS], False
