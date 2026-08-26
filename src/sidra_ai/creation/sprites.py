"""Procedural sprites, drawn from the palette and reproducible from a seed.

Two rules make this an asset generator rather than a random-shape generator.

**The palette is closed.** Every fill is a GAMEYARD token from site
``docs/DESIGN.md`` §2, and a test walks the generated SVG and rejects anything
else. A generator that invents colours would reintroduce the second design
system §2 exists to prevent, one sprite at a time, and nobody would notice
because each individual file looks fine.

**The randomness is seeded from the request.** The same request produces the
same sprites, byte for byte. Unseeded variety would mean an operator who
regenerates a project gets different art in a directory whose documents
already describe the old art - and would make the whole path untestable.

The shapes are simple on purpose: silhouettes built from a few primitives,
not attempts at illustration. A generator that tried for detail would produce
the "generic AI illustration" §3 prohibits.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from xml.etree import ElementTree

from sidra_ai.creation.games import GAMEYARD_TOKENS

#: Every colour a sprite may use. Deliberately the token set and nothing else,
#: including the neutral used for outlines, so "is this colour allowed" has a
#: single answer a test can enumerate.
PALETTE: tuple[str, ...] = (
    GAMEYARD_TOKENS["bg"],
    GAMEYARD_TOKENS["surface"],
    GAMEYARD_TOKENS["raised"],
    GAMEYARD_TOKENS["cyan"],
    GAMEYARD_TOKENS["magenta"],
    "none",
)

VIEWBOX = 64


@dataclass(frozen=True)
class Sprite:
    """One generated asset. ``name`` is what the page asks for it by."""

    name: str
    filename: str
    svg: str


def seed_for(request: str) -> int:
    """Derive the seed from the request, deterministically.

    ``hash()`` is salted per process, so a project regenerated tomorrow would
    not match the one described in its own documents. A digest does not move.
    """

    digest = hashlib.sha256(request.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _svg(body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" '
        f'width="{VIEWBOX}" height="{VIEWBOX}">{body}</svg>'
    )


def _fish(rng: random.Random) -> str:
    """A silhouette: body, tail, eye. Varied by proportion, not by detail."""

    body_h = rng.randint(16, 24)
    tail = rng.randint(10, 16)
    top = (VIEWBOX - body_h) // 2
    return _svg(
        f'<ellipse cx="30" cy="32" rx="20" ry="{body_h // 2}" '
        f'fill="{GAMEYARD_TOKENS["cyan"]}"/>'
        f'<polygon points="10,32 {10 - tail},{32 - tail // 2} {10 - tail},{32 + tail // 2}" '
        f'fill="{GAMEYARD_TOKENS["cyan"]}"/>'
        f'<circle cx="40" cy="{top + body_h // 3}" r="2.5" '
        f'fill="{GAMEYARD_TOKENS["bg"]}"/>'
    )


def _marker(rng: random.Random) -> str:
    """The thing the player aligns. Magenta, and small - §2 keeps it an accent."""

    width = rng.choice((4, 5, 6))
    return _svg(
        f'<rect x="{(VIEWBOX - width) // 2}" y="6" width="{width}" height="52" '
        f'rx="2" fill="{GAMEYARD_TOKENS["magenta"]}"/>'
    )


def _drop(rng: random.Random) -> str:
    corners = rng.choice((2, 6, 10))
    size = rng.randint(20, 30)
    offset = (VIEWBOX - size) // 2
    return _svg(
        f'<rect x="{offset}" y="{offset}" width="{size}" height="{size}" '
        f'rx="{corners}" fill="{GAMEYARD_TOKENS["cyan"]}"/>'
    )


def _basket(rng: random.Random) -> str:
    lip = rng.randint(4, 8)
    return _svg(
        f'<path d="M6 24 L58 24 L{58 - lip} 52 L{6 + lip} 52 Z" '
        f'fill="{GAMEYARD_TOKENS["magenta"]}"/>'
        f'<rect x="6" y="20" width="52" height="5" rx="2" '
        f'fill="{GAMEYARD_TOKENS["cyan"]}"/>'
    )


#: Which sprites each template needs, and what the page calls them. A template
#: with no entry gets no sprites rather than generic ones - the game still
#: plays, because the page falls back to the shapes it always drew.
SPRITE_SETS: dict[str, tuple[tuple[str, object], ...]] = {
    "fishing": (("target", _fish), ("marker", _marker)),
    "catch": (("target", _drop), ("marker", _basket)),
}


def generate_sprites(template: str, *, seed: int) -> tuple[Sprite, ...]:
    """Build this template's sprites. Same seed, same bytes."""

    rng = random.Random(seed)
    return tuple(
        Sprite(name, f"{name}.svg", draw(rng))
        for name, draw in SPRITE_SETS.get(template, ())
    )


def colours_in(svg: str) -> set[str]:
    """Every fill and stroke the document actually uses.

    Parsed rather than regexed: the check is "what would a renderer paint",
    and a regex over the text would also pass a colour hidden in an attribute
    no one reads.
    """

    root = ElementTree.fromstring(svg)
    found: set[str] = set()
    for element in root.iter():
        for attribute in ("fill", "stroke"):
            value = element.get(attribute)
            if value:
                found.add(value.strip().lower())
    return found


def off_palette(svg: str) -> set[str]:
    allowed = {colour.lower() for colour in PALETTE}
    return colours_in(svg) - allowed


def save_sprites(sprites: tuple[Sprite, ...], directory) -> tuple[str, ...]:
    """Write into an existing assets directory; return the filenames written."""

    from pathlib import Path

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    for sprite in sprites:
        (target / sprite.filename).write_text(sprite.svg, encoding="utf-8")
    return tuple(sprite.filename for sprite in sprites)


__all__ = [
    "PALETTE",
    "SPRITE_SETS",
    "Sprite",
    "VIEWBOX",
    "colours_in",
    "generate_sprites",
    "off_palette",
    "save_sprites",
    "seed_for",
]
