"""The one place a local model is allowed to touch a generated artifact.

``GeneratedGame.with_copy`` has existed since the game generator shipped and
had never been called: the official hole for the model was drilled and left
open, so the model's contribution to everything this project builds was
exactly zero bits (C-1027). This module is the plug, and its shape is chosen
so that plugging it in cannot make the product worse:

* **the page is finished before the model is asked.** Copy is overlaid on an
  artifact that already validated. A model that is missing, slow, wrong or
  malicious costs the page its wording, never its playability.
* **only wording crosses.** The request goes up as the operator wrote it; no
  retrieved corpus text is sent and none comes back into the page, so the
  guarantee that a playable page contains no indexed DATA still holds.
* **every failure is silent and identical.** Unreachable backend, prose
  instead of JSON, a 400-character title, a franchise name - all of them
  return ``None`` and leave the deterministic copy standing. There is one
  behaviour to reason about, not a family of partial ones.
* **echo never speaks.** The default backend summarizes retrieved blocks; its
  output is not a title. Asking it would put extractive prose in a page
  heading on every clean checkout, so the writer refuses before the call and
  the no-weights configuration keeps byte-for-byte the behaviour it had.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

from sidra_ai.models.base import GenerationRequest, LocalModelAdapter

#: Backends whose output is not model-written prose. ``echo`` is the default
#: on a checkout with no weights, so this is the common case, not the corner.
_SILENT_BACKENDS = frozenset({"echo", "abstract", ""})

#: Spellings the page-title guard does not carry because a request rarely
#: uses them, but a model reaches for readily. The guard's own list is added
#: to these rather than copied - two lists of franchise names drift, and the
#: one that drifts is the one nobody is reading.
_EXTRA_FORBIDDEN = (
    "zelda",
    "mario",
    "pokemon",
    "minecraft",
    "fortnite",
    "sonic",
    "tetris",
    "pac-man",
    "street fighter",
    "ゼルダの伝説",
    "スーパーマリオ",
    "テトリス",
    "ソニック",
)


@lru_cache(maxsize=1)
def _forbidden_names() -> tuple[str, ...]:
    """Every name a generated artifact may not carry, lowercased.

    Imported lazily: the router imports this module at module level and
    deliberately does not pay for the game templates until a generator is
    actually built.
    """

    from sidra_ai.creation.games import _TRADEMARKS

    return tuple(name.lower() for name in (*_TRADEMARKS, *_EXTRA_FORBIDDEN))


#: English instructions because small local models follow them most reliably,
#: with the output language pinned explicitly - the same reasoning, and the
#: same 2026-08-27 incident, behind rule 6 of the chat system prompt.
COPY_SYSTEM_PROMPT = """You write the name and one line of flavour for a page
that is already finished. You are not writing the page.

Rules:
1. Reply with one JSON object and nothing else, no prose, no code fence:
   {"title": "...", "tagline": "..."}
2. Write both fields in the language of the request. 日本語の依頼には日本語で
   答えること。Never switch to English for a Japanese request.
3. title: at most 20 characters. tagline: at most 30 characters. One line
   each, no line breaks.
4. Never use the name of an existing commercial work, character or series,
   even if the request asks for one.
5. No HTML, no markup, no URL, no quotation marks inside the values.
6. The flavour line describes the mood, not the controls: the page prints its
   own instructions already.
"""

_MAX_TITLE = 20
_MAX_TAGLINE = 30
#: Anything that would be markup, a link, or a second line once escaped into
#: the page. ``with_copy`` escapes what it inserts, so this is belt and
#: braces - and it keeps a rejected value out of the artifact entirely rather
#: than putting a visibly mangled one in.
_UNSAFE = re.compile(r"[<>&\"'\\\x00-\x1f\x7f]|https?://|```")


@dataclass(frozen=True)
class ArtifactCopy:
    """Wording a model proposed and the guards accepted."""

    title: str
    tagline: str = ""


#: What a generator is handed. ``None`` means "keep what you had", which is
#: the answer for every failure as well as for no model at all.
CopyWriter = Callable[..., "ArtifactCopy | None"]


def _acceptable(value: str, limit: int) -> bool:
    text = value.strip()
    if not text or len(text) > limit:
        return False
    if _UNSAFE.search(text):
        return False
    lowered = text.lower()
    return not any(name in lowered for name in _forbidden_names())


def parse_copy(text: str) -> ArtifactCopy | None:
    """Read the model's reply, or decide it did not answer the question.

    Kept separate from the call so the guards can be tested without a model
    and so a future backend that returns JSON natively can reuse them.
    """

    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    title = payload.get("title")
    tagline = payload.get("tagline", "")
    if not isinstance(title, str) or not isinstance(tagline, str):
        return None
    if not _acceptable(title, _MAX_TITLE):
        return None
    # A rejected tagline does not sink an accepted title: the page has a
    # deterministic tagline to fall back on, field by field.
    clean_tagline = tagline.strip() if _acceptable(tagline, _MAX_TAGLINE) else ""
    return ArtifactCopy(title.strip(), clean_tagline)


def build_copy_writer(model: LocalModelAdapter | None) -> CopyWriter:
    """Wrap a backend as the copy provider generators take.

    Always returns a callable, so a caller never branches on whether a model
    exists - the branch lives here, once, where the echo rule is stated.
    """

    def write(request: str, *, kind: str = "game", default_title: str = "") -> ArtifactCopy | None:
        if model is None:
            return None
        if str(getattr(model, "backend", "")) in _SILENT_BACKENDS:
            return None
        if getattr(model, "requires_paid_api", False):
            # Unreachable through the registry, which refuses these at
            # construction. Restated here because this is a *new* call site:
            # a backend that bills per token must not acquire one by being
            # wired into the generator.
            return None
        message = (
            f"依頼: {request.strip()}\n"
            f"作ったもの: {kind}\n"
            f"既定の題: {default_title}\n"
            "この作品の題と一言を JSON で。"
        )
        try:
            result = model.generate(
                GenerationRequest(
                    system_prompt=COPY_SYSTEM_PROMPT,
                    user_message=message,
                    # No retrieved DATA: a playable page must not carry
                    # indexed content, so none is offered to the model that
                    # names it.
                    data_context="",
                    max_output_tokens=120,
                    temperature=0.4,
                )
            )
        except Exception:  # noqa: BLE001 - naming a page may never break making one
            return None
        return parse_copy(getattr(result, "text", "") or "")

    return write


def copy_metadata(copy: ArtifactCopy | None) -> dict[str, Any]:
    """What the outcome reports about the model's contribution.

    Present on every artifact rather than only the ones a model touched: a
    field that appears exactly when something happened is a field nobody
    writes a check against.
    """

    return {
        "model_copy": copy is not None,
        "model_title": copy.title if copy else "",
        "model_tagline": copy.tagline if copy else "",
    }


__all__ = [
    "ArtifactCopy",
    "COPY_SYSTEM_PROMPT",
    "CopyWriter",
    "build_copy_writer",
    "copy_metadata",
    "parse_copy",
]
