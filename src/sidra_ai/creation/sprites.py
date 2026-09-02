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
import re
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
def _hero(rng: random.Random) -> str:
    """The hat is the character. Body cyan, hat dark - a silhouette, not art."""

    brim = rng.randint(20, 26)
    return _svg(
        f'<rect x="{(VIEWBOX - 24) // 2}" y="26" width="24" height="28" rx="4" '
        f'fill="{GAMEYARD_TOKENS["cyan"]}"/>'
        f'<rect x="{(VIEWBOX - brim) // 2}" y="18" width="{brim}" height="8" rx="3" '
        f'fill="{GAMEYARD_TOKENS["raised"]}"/>'
        f'<rect x="{(VIEWBOX - 12) // 2}" y="8" width="12" height="12" rx="3" '
        f'fill="{GAMEYARD_TOKENS["raised"]}"/>'
    )


def _blob(rng: random.Random) -> str:
    """An enemy: a magenta lump with two dark eyes. Menace by contrast alone."""

    body = rng.randint(34, 44)
    offset = (VIEWBOX - body) // 2
    eye_y = offset + body // 3
    return _svg(
        f'<rect x="{offset}" y="{offset}" width="{body}" height="{body}" '
        f'rx="{body // 3}" fill="{GAMEYARD_TOKENS["magenta"]}"/>'
        f'<circle cx="{offset + body // 3}" cy="{eye_y}" r="3" '
        f'fill="{GAMEYARD_TOKENS["bg"]}"/>'
        f'<circle cx="{offset + 2 * body // 3}" cy="{eye_y}" r="3" '
        f'fill="{GAMEYARD_TOKENS["bg"]}"/>'
    )


def _rock(rng: random.Random) -> str:
    jut = rng.randint(6, 12)
    return _svg(
        f'<path d="M8 52 L{8 + jut} 20 L32 12 L{56 - jut} 22 L56 52 Z" '
        f'fill="{GAMEYARD_TOKENS["raised"]}"/>'
    )


def _bush(rng: random.Random) -> str:
    r = rng.randint(12, 16)
    return _svg(
        f'<circle cx="22" cy="38" r="{r}" fill="{GAMEYARD_TOKENS["surface"]}"/>'
        f'<circle cx="42" cy="36" r="{r - 2}" fill="{GAMEYARD_TOKENS["surface"]}"/>'
        f'<circle cx="32" cy="26" r="{r - 3}" fill="{GAMEYARD_TOKENS["surface"]}"/>'
        f'<circle cx="32" cy="34" r="4" fill="{GAMEYARD_TOKENS["cyan"]}"/>'
    )


def _villager(rng: random.Random) -> str:
    hood = rng.randint(18, 24)
    return _svg(
        f'<rect x="{(VIEWBOX - 22) // 2}" y="28" width="22" height="26" rx="4" '
        f'fill="{GAMEYARD_TOKENS["surface"]}"/>'
        f'<circle cx="32" cy="22" r="{hood // 2}" fill="{GAMEYARD_TOKENS["magenta"]}"/>'
    )


#: Which sprites each template needs, and what the page calls them. A template
#: with no entry gets no sprites rather than generic ones - the game still
#: plays, because the page falls back to the shapes it always drew.
def _interceptor(rng: random.Random) -> str:
    """A foe seen from above: a wing span with a lit core.

    Wider than it is tall, and the core sits off-centre by a seeded pixel or
    two, so a formation of them does not read as one stamped shape.
    """

    span = rng.randint(38, 46)
    height = span // 2
    left = (VIEWBOX - span) // 2
    top = (VIEWBOX - height) // 2
    core = left + span // 2 + rng.randint(-2, 2)
    return _svg(
        f'<path d="M{left} {top} L{left + span} {top} '
        f'L{core} {top + height} Z" fill="{GAMEYARD_TOKENS["magenta"]}"/>'
        f'<rect x="{core - 3}" y="{top + 2}" width="6" height="{height // 2}" '
        f'fill="{GAMEYARD_TOKENS["cyan"]}"/>'
    )



SPRITE_SETS: dict[str, tuple[tuple[str, object], ...]] = {
    "fishing": (("target", _fish), ("marker", _marker)),
    "catch": (("target", _drop), ("marker", _basket)),
    "adventure": (
        ("hero", _hero),
        ("enemy", _blob),
        ("rock", _rock),
        ("bush", _bush),
        ("npc", _villager),
    ),
    # The shooter draws its own ship and shots as paths; only the foe is
    # worth a sprite, because a wave of them is what the eye reads first.
    "shooter": (("foe", _interceptor),),
    # The kaiju fight draws everything as paths on purpose: the whole point
    # of the template is that the monster is a silhouette crossing the frame
    # rather than a picture of a monster, and a sprite would be a picture.
    "kaiju": (),
    # The race recolours its whole frame once per lap through the scene
    # palette; the car and the obstacles are flat shapes so they take that
    # light. A sprite's baked-in colours would sit unchanged in a frame
    # whose mood is the lap counter.
    "racing": (),
    # The platformer's readability lives in edges: the walkable lip of every
    # platform is a value step plus a highlight (§4), and a picture pasted
    # over it would hide exactly the line the player lands by.
    "platformer": (),
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


# ---------------------------------------------------------- slot contract
#
# C-1116. The knowledge base (§9 学び (2)) puts image generation on the
# other side of a decision the owner has to make on their own machine: a
# local image model is weights, disk and a GPU, and none of that is a loop's
# to install. What *is* a loop's job is the receptacle - so that the day a
# model exists, the art is a file drop and not a rewrite.
#
# The convention, in three sentences:
#
# 1. Every picture a page draws goes through ``sprite(name, ...)``, and
#    every such ``name`` is a **slot** declared here with a role.
# 2. A slot is filled by ``assets/<name>.<ext>``. The procedural generator
#    writes ``<name>.svg``; anything else with that stem - a PNG a model
#    produced, a drawing someone made - wins over it.
# 3. Nothing depends on a slot being filled. A missing or unreadable file
#    leaves the page playable, drawing the flat shape it always drew.
#
# The third is why this is safe to ship before any model exists, and the
# first is why a template cannot quietly grow a picture nobody can replace.

#: What each slot is *for*, in the page's own terms. Written down because a
#: slot's name is what the page calls it, not what an artist filling it
#: needs to know: "foe" says nothing about a shape seen from above.
#: Slots a page asks for that no generator fills today, and why. Declared
#: rather than left implicit: the duel has called ``sprite('fighter')``
#: since it was written, and an undeclared call is a picture nobody can
#: replace and nobody can see is missing.
UNFILLED_SLOTS: dict[str, dict[str, str]] = {
    "duel": {
        "fighter": (
            "決闘者は手続き描画が本体で、スロットはその下に敷く任意の絵。"
            "fallback は空文字＝何も描かない。手続きの体が上に載るので、"
            "現行の生成スプライトを入れてもほぼ見えない。"
            "画像モデル導入後に、体の描画順ごと見直す前提の受け皿。"
        )
    },
}

SLOT_ROLES: dict[str, str] = {
    "target": "プレイヤーが狙う / 受ける対象",
    "marker": "プレイヤーが動かすもの（マーカー・受け皿）",
    "hero": "操作キャラクター",
    "enemy": "敵",
    "rock": "通れない地形",
    "bush": "見た目だけの茂み",
    "npc": "話しかける相手",
    "foe": "上から見た迎撃機",
    "fighter": "横から見た決闘者",
}

#: Image extensions an operator (or, later, a local model) may drop in. SVG
#: last: it is what the generator writes, so it is the thing being replaced.
#: No formats that execute anything, and nothing is fetched - the page loads
#: a relative path inside the project directory.
REPLACEABLE_SUFFIXES: tuple[str, ...] = (".png", ".webp", ".jpg", ".jpeg", ".svg")

#: How the page asks for a picture. One spelling, so a call that no slot
#: declares is findable rather than a thing someone notices in a screenshot.
_SPRITE_CALL = re.compile(r"""sprite\(\s*['"]([^'"]+)['"]""")


@dataclass(frozen=True)
class SpriteSlot:
    """One replaceable picture: what the page calls it, and what it is for."""

    name: str
    role: str
    #: True when a procedural generator fills it today. False would mean the
    #: page draws its fallback shape until somebody supplies a file.
    generated: bool


def slots_for(template: str) -> tuple[SpriteSlot, ...]:
    """Every slot this template declares, filled today or not."""

    filled = tuple(
        SpriteSlot(name, SLOT_ROLES.get(name, ""), True)
        for name, _ in SPRITE_SETS.get(template, ())
    )
    empty = tuple(
        SpriteSlot(name, SLOT_ROLES.get(name, ""), False)
        for name in sorted(UNFILLED_SLOTS.get(template, {}))
    )
    return filled + empty


def slot_calls(script: str) -> set[str]:
    """Every name the template's own drawing code asks for."""

    return set(_SPRITE_CALL.findall(script))


def contract_gaps(template: str, script: str) -> list[str]:
    """Where the declaration and the page disagree.

    Both directions are failures, and for different reasons: a call with no
    slot is a picture nobody can replace (the duel drew a grey rectangle for
    weeks this way), and a slot with no call is a file written into a
    project that nothing ever loads.
    """

    declared = {slot.name for slot in slots_for(template)}
    called = slot_calls(script)
    gaps = [f"{name}: drawn but not declared" for name in sorted(called - declared)]
    gaps += [f"{name}: declared but never drawn" for name in sorted(declared - called)]
    gaps += [
        f"{name}: left unfilled with no reason written down"
        for name, why in sorted(UNFILLED_SLOTS.get(template, {}).items())
        if not why.strip()
    ]
    gaps += [
        f"{name}: no role written down"
        for name in sorted(declared & called)
        if not SLOT_ROLES.get(name)
    ]
    return gaps


def resolve_slots(template: str, assets_dir) -> dict[str, str]:
    """Slot name -> the relative path the page should load, if anything.

    An operator's own file wins over the generated one, which is the whole
    point: the receptacle is filled by putting a file in a directory. A slot
    with no file at all is simply absent from the mapping, and the page
    falls back to the shape it always drew.
    """

    from pathlib import Path

    directory = Path(assets_dir)
    found: dict[str, str] = {}
    for slot in slots_for(template):
        for suffix in REPLACEABLE_SUFFIXES:
            candidate = directory / f"{slot.name}{suffix}"
            # is_file() rather than exists(): a directory named target.png
            # is not a picture, and following it would be a surprise.
            if candidate.is_file():
                found[slot.name] = f"{directory.name}/{candidate.name}"
                break
    return found


#: The fallback claim, run rather than asserted: a slot whose file never
#: decodes has to leave the flat shape the template always drew, and a slot
#: whose file *does* decode has to replace it. Both directions, because a
#: loader that always fell back would pass the first check alone - and that
#: is precisely the state "we shipped the receptacle" would hide.
LOADER_PROBE = """
const painted = [];
const drawn = [];
const cx = { fillStyle: '', fillRect: (x,y,w,h) => painted.push(cx.fillStyle),
  drawImage: () => drawn.push(1) };
globalThis.Image = function(){ return { complete: DECODED_INPUT,
  naturalWidth: DECODED_INPUT ? 64 : 0 } };
LOADER_PLACEHOLDER
sprite('target', 0, 0, 16, 16, '#abcdef');
console.log(JSON.stringify({ painted: painted, drawn: drawn.length,
  slots: Object.keys(SPRITES) }));
"""


def loader_probe(*, decoded: bool, slots: dict[str, str] | None = None) -> str:
    """The page's own sprite loader, with the image decode pinned."""

    import json as _json

    from sidra_ai.creation.games import _SPRITE_LOADER

    loader = _SPRITE_LOADER.replace(
        "SPRITE_MAP_TOKEN", _json.dumps(slots or {"target": "assets/target.svg"})
    )
    return LOADER_PROBE.replace("DECODED_INPUT", "true" if decoded else "false").replace(
        "LOADER_PLACEHOLDER", loader
    )


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
    "LOADER_PROBE",
    "REPLACEABLE_SUFFIXES",
    "UNFILLED_SLOTS",
    "SLOT_ROLES",
    "SPRITE_SETS",
    "Sprite",
    "SpriteSlot",
    "contract_gaps",
    "loader_probe",
    "resolve_slots",
    "slot_calls",
    "slots_for",
    "VIEWBOX",
    "colours_in",
    "generate_sprites",
    "off_palette",
    "save_sprites",
    "seed_for",
]
