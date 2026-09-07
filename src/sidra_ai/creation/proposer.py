"""Let the model choose the page's parameters - inside the shipped envelope.

The gap this closes is the one GPT-6 makes obvious (C-1135): a big model
writes anything and nothing checks it; SIDRA checks everything and writes
the same page twice. 「レース作って」 twice gives two identical files,
because every number comes from a table.

The answer is not a random seed. A seed makes variety nobody chose; this
lets the *model* choose - and then throws away anything it chose that the
author did not ship. Three properties, each measured
(``creation_variety_verified`` in ``scripts/product_metrics.py``) rather
than asserted:

* **The envelope is still the designed one.** A proposal is folded into the
  same ``panel`` overrides a sentence already produces (C-1117), so
  ``panel_schema`` clamps every axis to the template's own easy..hard span.
  A model that asks for a speed of 9000 gets the hardest value the author
  shipped, not an unplayable page.
* **Nothing but the known keys survives.** The reply is parsed as JSON and
  every key not in the schema is dropped. ``accent`` is checked for the
  shape of a colour before it can reach the page - it is substituted into
  the artifact as an identifier, so an unvalidated string there is the one
  place a model could write something that is not a parameter at all.
* **Silence changes nothing.** With no weights - the default on a checkout -
  the backend is ``echo``, the proposer declines, and the page is the one
  today's table builds, byte for byte. The feature is invisible until a
  model is actually present, which is what makes it measurable here.

The model is asked about numbers only. It never sees retrieved content, so
there is nothing here for indexed DATA to steer.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from sidra_ai.models.base import GenerationRequest, LocalModelAdapter

#: Backends whose output is not a model's answer. Same list, same reason as
#: ``copy_writer``: ``echo`` is the default with no weights, so this is the
#: common path rather than a corner.
SILENT_BACKENDS = frozenset({"echo", "abstract", ""})

#: English instructions, Japanese output - the house rule (SYSTEM_PROMPT
#: rule 6's sibling). Nothing here asks for prose; the reply is JSON.
PROPOSER_SYSTEM_PROMPT = """You choose the starting parameters of a small
browser game. Reply with ONE JSON object and nothing else.

Keys you may use (all optional):
  "band"    number  - the template's second axis, inside the given range
  "accent"  string  - a hex colour like "#4fd1c5"
  "daily"   boolean - start with the shared daily board on
  "ghost"   boolean - start with the previous run's trail shown
  "brief"   boolean - show the briefing screen every visit

Rules:
1. Never invent a key that is not listed above.
2. Stay inside the range you are given. A value outside it is discarded.
3. Vary your choices between requests; two players asking the same thing
   should not get the same page.
"""

#: ``#rgb`` or ``#rrggbb``. The accent is substituted into the page as an
#: identifier, so this is the one field where a wrong shape is not merely a
#: bad parameter.
_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

#: The first JSON object in the reply. Small models like to explain
#: themselves first, and a proposal wrapped in an apology is still a
#: proposal.
_OBJECT = re.compile(r"\{.*?\}", re.S)

#: What may come back. Anything else is dropped rather than clamped - a key
#: this does not know is a key nothing downstream reads.
_BOOLEANS = ("daily", "ghost", "brief")


def parse_proposal(text: str, *, bands: tuple[float, ...]) -> dict:
    """The overrides worth keeping out of a model's reply.

    Separate from the call so the guards can be tested without a model -
    the same split ``copy_writer.parse_copy`` uses, and for the same reason:
    what protects the page is the parsing, not the asking.
    """

    found = _OBJECT.search(text or "")
    if not found:
        return {}
    try:
        raw = json.loads(found.group(0))
    except (ValueError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    band = raw.get("band")
    # bool is an int in Python, and "band": true is not a number.
    if isinstance(band, (int, float)) and not isinstance(band, bool):
        low, high = min(bands), max(bands)
        out["band"] = min(high, max(low, float(band)))
    accent = raw.get("accent")
    if isinstance(accent, str) and _COLOUR.match(accent.strip()):
        out["accent"] = accent.strip().lower()
    for name in _BOOLEANS:
        if isinstance(raw.get(name), bool):
            out[name] = raw[name]
    return out


ParamProposer = Callable[[str, str, tuple[float, ...]], dict]


def build_param_proposer(model: LocalModelAdapter | None) -> ParamProposer:
    """Always returns a callable, so no caller branches on having a model."""

    def propose(request: str, template: str, bands: tuple[float, ...]) -> dict:
        if model is None:
            return {}
        if str(getattr(model, "backend", "")) in SILENT_BACKENDS:
            return {}
        if getattr(model, "requires_paid_api", False):
            return {}
        low, high = min(bands), max(bands)
        try:
            result = model.generate(
                GenerationRequest(
                    system_prompt=PROPOSER_SYSTEM_PROMPT,
                    user_message=(
                        f"template: {template}\n"
                        f"band range: {low} to {high}\n"
                        f"request: {request}"
                    ),
                    # No retrieved content reaches this call: the model is
                    # choosing numbers, and DATA has no business in that.
                    data_context="",
                    max_output_tokens=120,
                )
            )
        except Exception:  # noqa: BLE001 - a silent model is a working page
            return {}
        return parse_proposal(getattr(result, "text", "") or "", bands=bands)

    return propose


__all__ = [
    "PROPOSER_SYSTEM_PROMPT",
    "ParamProposer",
    "SILENT_BACKENDS",
    "build_param_proposer",
    "parse_proposal",
]
