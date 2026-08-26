"""The GIF encoder must produce files other decoders can open.

The encoder is hand-written (no Pillow on the machines that matter), which
is exactly why the checks here are adversarial: a block-walk over the real
bytes, an **independent LZW decoder written from the specification** - full
dictionary semantics, code-width growth and all, none of which the encoder
itself uses - and, where Pillow happens to be installed, a decode through it
as a second opinion. An encoder bug that survives all three is one a real
viewer would forgive too.
"""

from __future__ import annotations

import re

import pytest

from sidra_ai.creation.gifs import (
    FRAMES,
    HEIGHT,
    PALETTE,
    WIDTH,
    choose_motif,
    generate_gif,
    parse_gif,
    save_gif,
    validate_gif,
)
from sidra_ai.creation.intent import CreationKind, detect_creation_intent
from sidra_ai.creation.router import build_default_router


@pytest.mark.parametrize("request_text", ["魚のGIFを作って", "GIFを作って"])
def test_every_motif_generates_a_valid_looping_animation(request_text: str) -> None:
    gif = generate_gif(request_text)
    verdict = validate_gif(gif)
    assert verdict["valid"], verdict["failures"]
    assert verdict["frames"] == FRAMES
    assert verdict["looped"]


def test_generation_is_deterministic_for_the_same_request() -> None:
    assert generate_gif("魚のGIFを作って").data == generate_gif("魚のGIFを作って").data


def test_different_requests_vary_the_animation() -> None:
    assert generate_gif("魚のGIFを作って").data != generate_gif("大きな魚のGIFを作って").data


def test_motif_is_chosen_from_the_request() -> None:
    assert choose_motif("釣りの魚が泳ぐGIF") == "fish"
    assert choose_motif("なにか動く画像を") == "pulse"


def test_the_palette_stays_on_gameyard_tokens() -> None:
    """DESIGN.md's colours and nothing else in the table's used entries."""

    assert PALETTE[0] == (0x05, 0x07, 0x0F)
    assert (0x2E, 0xE6, 0xFF) in PALETTE
    assert (0xFF, 0x5C, 0xC8) in PALETTE


# ------------------------------------------- the independent decoder


def _decode_frames(data: bytes) -> list[list[int]]:
    """A GIF LZW decoder written from the spec, sharing nothing with the

    encoder. It implements what the encoder deliberately avoids needing -
    the growing dictionary and the widening code size - so an encoder
    mistake about either (a late CLEAR, a wrong initial width) surfaces
    here as garbage output rather than passing silently."""

    assert data[:6] == b"GIF89a"
    packed = data[10]
    pos = 13 + (3 * (2 << (packed & 0x07)) if packed & 0x80 else 0)
    frames: list[list[int]] = []
    while pos < len(data) and data[pos] != 0x3B:
        if data[pos] == 0x21:
            pos += 2
            while data[pos]:
                pos += 1 + data[pos]
            pos += 1
            continue
        assert data[pos] == 0x2C
        local = data[pos + 9]
        pos += 10 + (3 * (2 << (local & 0x07)) if local & 0x80 else 0)
        min_code = data[pos]
        pos += 1
        stream = bytearray()
        while data[pos]:
            count = data[pos]
            stream += data[pos + 1 : pos + 1 + count]
            pos += 1 + count
        pos += 1

        clear, end = 1 << min_code, (1 << min_code) + 1
        table: list[list[int]] = []
        width = min_code + 1
        out: list[int] = []
        prev: list[int] | None = None
        accumulator = bits = 0

        def reset() -> None:
            nonlocal table, width, prev
            table = [[i] for i in range(1 << min_code)] + [[], []]
            width = min_code + 1
            prev = None

        reset()
        for byte in stream:
            accumulator |= byte << bits
            bits += 8
            while bits >= width:
                code = accumulator & ((1 << width) - 1)
                accumulator >>= width
                bits -= width
                if code == clear:
                    reset()
                    continue
                if code == end:
                    bits = 0
                    accumulator = 0
                    break
                if code < len(table):
                    entry = list(table[code])
                    if prev is not None:
                        table.append(prev + [entry[0]])
                else:
                    assert prev is not None and code == len(table), "bad LZW code"
                    entry = prev + [prev[0]]
                    table.append(entry)
                out += entry
                prev = entry
                if len(table) == (1 << width) and width < 12:
                    width += 1
        frames.append(out)
    return frames


def test_an_independent_lzw_decoder_recovers_every_frame() -> None:
    gif = generate_gif("魚のGIFを作って")

    frames = _decode_frames(gif.data)

    assert len(frames) == FRAMES
    for pixels in frames:
        assert len(pixels) == WIDTH * HEIGHT
        assert all(0 <= index < len(PALETTE) for index in pixels)
    # It animates: the fish moved, so consecutive frames differ.
    assert frames[0] != frames[5]
    # And the fish is actually cyan on the dark foundation.
    assert 2 in frames[0] and 0 in frames[0]


def test_pillow_agrees_when_available() -> None:
    """A second, foreign opinion - skipped, not faked, where Pillow is absent."""

    pillow = pytest.importorskip("PIL.Image")
    from io import BytesIO

    gif = generate_gif("GIFを作って")
    image = pillow.open(BytesIO(gif.data))
    image.load()

    assert image.format == "GIF"
    assert image.size == (WIDTH, HEIGHT)
    assert image.info.get("loop") == 0
    assert getattr(image, "n_frames", 1) == FRAMES


# --------------------------------------------------- saving and routing


def test_save_writes_a_name_the_listing_will_carry(tmp_path) -> None:
    from sidra_ai.api.artifacts import SAFE_NAME

    gif = generate_gif("魚のGIFを作って")
    path = save_gif(gif, tmp_path)

    assert path.exists()
    assert path.parent == tmp_path / "artifacts"
    assert SAFE_NAME.match(path.name)
    assert re.match(r"gif-fish-\d{8}T\d{6}Z\.gif$", path.name)


def test_intent_routes_gif_requests_but_not_questions() -> None:
    assert detect_creation_intent("魚のGIFを作って").kind is CreationKind.GIF
    assert detect_creation_intent("動く画像を作って").kind is CreationKind.GIF
    assert not detect_creation_intent("GIFとは").is_creation
    # Neighbouring kinds keep their ground: a game is not a GIF, and the
    # game page's own animation stays with the project pipeline.
    assert detect_creation_intent("釣りゲームを作って").kind is CreationKind.GAME
    assert detect_creation_intent("スプライトを作って").kind is CreationKind.PROJECT


def test_router_builds_a_gif_end_to_end(tmp_path) -> None:
    router = build_default_router(data_dir=str(tmp_path))
    request = "魚のGIFを作って"
    outcome = router.route(request, detect_creation_intent(request))

    assert outcome.handled
    assert outcome.details["valid"] is True
    assert outcome.details["frames"] == FRAMES
    assert outcome.artifact_path.endswith(".gif")
