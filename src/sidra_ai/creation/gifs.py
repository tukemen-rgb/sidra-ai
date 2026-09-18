"""Animated GIFs, written byte by byte, with nothing to install.

The backlog item said "Pillow で"; this module deviates the same direction
C-1004 did, and records it there: the encoder is written by hand instead of
imported, because Pillow is not on this container and not on the operator's
machine, and a generator that answers 「GIF 作って」 with "please pip install
something first" has not generated anything. GIF89a is a small format - a
header, a colour table, per-frame control blocks, LZW-packed indices, a
trailer - and the subset used here (small global palette, literal-only LZW)
is byte-exact and boring on purpose. If Pillow arrives later via the
``[creation]`` extra it can replace the packer; the interface stays.

Everything else follows the package rules: deterministic via a seed derived
from the request, GAMEYARD palette only, files stay on the operator's disk,
and validation parses the actual bytes rather than trusting the writer -
:func:`parse_gif` is a real block-walker, so a truncated or malformed file
fails the way a foreign one would.

The LZW packing uses the classic literal-only trick: with a 128-entry
colour table the minimum code size is 7, every pixel is emitted as its own
literal code, and a CLEAR is inserted before the decoder's dictionary would
force the code width past 8 bits. Larger files than real compression, but a
correct decoder-independent stream with no compression state to get wrong.
"""

from __future__ import annotations

import re
import struct
import unicodedata
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sidra_ai.creation.artifact_paths import unique_path
from sidra_ai.creation.vocabulary import (
    digits_for_spelled,
    drop_english_frame,
    drop_request_adverbs,
    drop_size_phrases,
)

WIDTH = 120
HEIGHT = 90
FRAMES = 10
#: Hundredths of a second per frame; 8 makes the loop ~0.8s.
DELAY_CS = 8

#: 「30フレーム」「30 コマ」 - a length someone asked for, counted in frames.
#: The unit word is what makes the number a length, which is why no list of
#: not-a-length words is needed: 「2026年のGIF」 has no digits in front of one
#: (the same measurement that deleted such a list in decks.py, C-1821).
#: C-1934: and the English forms. 「make a 30 frame gif」, 「a 30-frame gif」,
#: 「a gif with 30 frames」 were all read as naming no length, so the caveat
#: C-1823 wrote never fired for them - an English request was given the
#: fixed 10 frames and told nothing, while the Japanese twin is told.
_FRAME_COUNT = re.compile(
    r"(\d{1,3})\s*(?:フレーム|コマ)|(?<![A-Za-z0-9])(\d{1,3})[\s-]*frames?\b",
    re.IGNORECASE,
)

#: 「5秒」「5 秒間」 - the same length asked for in time instead.
#: C-1934: 「make a 5 second gif」, 「a 5 sec gif」. Deliberately NOT a bare
#: 「5s」: 「make a gif of the 90s」 would then be read as asking for ninety
#: seconds, and a caveat that fires with nothing to report is the thing
#: C-1823 says stops being read. Whole seconds only, like the Japanese
#: side - 「2.5 second」 is not read by either, which is a limit rather than
#: a difference between the languages.
_SECONDS = re.compile(
    r"(\d{1,3})\s*秒|(?<![A-Za-z0-9])(\d{1,3})[\s-]*(?:seconds?|secs?)\b",
    re.IGNORECASE,
)


def requested_frames(request: str) -> int | None:
    """How many frames the request asked for, or None when it named none."""

    # C-1955: spelled numbers become digits first.
    for match in _FRAME_COUNT.finditer(digits_for_spelled(request)):
        # Whichever branch matched - the Japanese unit or the English one.
        found = int(next(group for group in match.groups() if group))
        if found > 0:
            return found
    return None


def requested_seconds(request: str) -> int | None:
    """How many seconds the request asked for, or None when it named none."""

    # C-1955: the same reading for seconds - 「五秒の GIF」 and
    # 「a five second gif」 name a length as much as 「5秒」 does.
    for match in _SECONDS.finditer(digits_for_spelled(request)):
        found = int(next(group for group in match.groups() if group))
        if found > 0:
            return found
    return None


def loop_seconds(frames: int) -> float:
    """How long one loop of that many frames actually lasts."""

    return frames * DELAY_CS / 100


def length_note(request: str, made_frames: int, *, in_japanese: bool = True) -> str:
    """The admission that the animation is not the length asked for, or "".

    C-1823. ``FRAMES`` and ``DELAY_CS`` are constants and there is no length
    to set, so 「30フレームのGIFを作って」 answered

        「30フレーム」のアニメ GIF を作りました（絵柄: …・10 フレーム・…）

    - the asked-for number became the artifact's name and a different, true
    number sat in the parenthesis of the same sentence. 「5秒のGIF」 was worse:
    the real 0.8 second loop was stated nowhere, because the summary reports
    frames and the request spoke of time.

    This generator already admits the motif it could not draw (C-1258) and the
    colour it could not use (C-1272). The length was the one left silent, the
    same asymmetry the deck had about its slide count (C-1821).

    Both numbers are derived - the frames from the validated bytes, the
    seconds from ``DELAY_CS`` - so a change to either constant carries into
    this sentence instead of leaving it behind.

    Silent when the request named no length, and silent when the length asked
    for is the length that was made: a caveat that fires with nothing to
    report stops being read.
    """

    # C-1932: said in the language the reply takes. The caller decides that
    # with the product's own rule and passes the answer in, rather than this
    # helper growing a second language test of its own.
    said: list[str] = []
    frames = requested_frames(request)
    if frames is not None and frames != made_frames:
        said.append(
            (
                f"依頼は {frames} フレームでしたが、"
                f"いまは決まった {made_frames} フレームで作ります。"
                "フレーム数は指定できません。"
            )
            if in_japanese
            else (
                f" The request asked for {frames} frames, but this is made at a "
                f"fixed {made_frames} frames. The frame count cannot be set."
            )
        )
    seconds = requested_seconds(request)
    actual = loop_seconds(made_frames)
    if seconds is not None and seconds != actual:
        said.append(
            (
                f"依頼は {seconds} 秒でしたが、"
                f"いまは 1 周 {actual:g} 秒"
                f"（{made_frames} フレーム × {DELAY_CS / 100:g} 秒）のループで作ります。"
                "長さは指定できません。"
            )
            if in_japanese
            else (
                f" The request asked for {seconds} seconds, but this is made as "
                f"a {actual:g} second loop ({made_frames} frames x "
                f"{DELAY_CS / 100:g} s). The length cannot be set."
            )
        )
    return "".join(said)


#: The DESIGN.md tokens and nothing else. Index 0 is the background and the
#: table is padded to 128 entries so the literal-only packer's fixed code
#: size is always valid.
PALETTE: tuple[tuple[int, int, int], ...] = (
    (0x05, 0x07, 0x0F),  # 0 bg: the dark foundation
    (0x0A, 0x0F, 0x1C),  # 1 raised surface
    (0x2E, 0xE6, 0xFF),  # 2 gy_cyan
    (0xFF, 0x5C, 0xC8),  # 3 gy_magenta (sparingly, per DESIGN.md)
    (0x9A, 0xF2, 0xFF),  # 4 pale cyan highlight
)

_TABLE_SIZE = 128  # 2^(6+1); flag value 6 in the logical screen descriptor
_MIN_CODE_SIZE = 7
_CLEAR = 1 << _MIN_CODE_SIZE
_END = _CLEAR + 1


@dataclass(frozen=True)
class GeneratedGif:
    """One animation and how it was derived."""

    title: str
    motif: str
    seed: int
    data: bytes
    #: False when the request named no motif word and the default was used.
    #: The animation is identical either way; this lets the summary tell a
    #: reader who asked for 「猫」 that they got the default (C-1258).
    motif_named: bool = True
    evidence: tuple[str, ...] = field(default_factory=tuple)


class _Lcg:
    """A tiny deterministic generator; ``random`` would be fine, but its

    sequence is a stdlib implementation detail and these bytes are pinned by
    tests across versions."""

    def __init__(self, seed: int) -> None:
        self.state = (seed & 0x7FFFFFFF) or 1

    def next(self) -> int:
        self.state = (self.state * 48271) % 0x7FFFFFFF
        return self.state

    def below(self, bound: int) -> int:
        return self.next() % bound


# ------------------------------------------------------------- drawing


class _Canvas:
    """A grid of palette indices - the whole graphics stack this needs."""

    def __init__(self) -> None:
        self.pixels = bytearray([0]) * 1  # replaced below; keeps mypy simple
        self.pixels = bytearray(WIDTH * HEIGHT)

    def fill_rect(self, x0: int, y0: int, w: int, h: int, colour: int) -> None:
        for y in range(max(0, y0), min(HEIGHT, y0 + h)):
            row = y * WIDTH
            for x in range(max(0, x0), min(WIDTH, x0 + w)):
                self.pixels[row + x] = colour

    def fill_ellipse(self, cx: float, cy: float, rx: float, ry: float, colour: int) -> None:
        if rx <= 0 or ry <= 0:
            return
        for y in range(max(0, int(cy - ry)), min(HEIGHT, int(cy + ry) + 1)):
            for x in range(max(0, int(cx - rx)), min(WIDTH, int(cx + rx) + 1)):
                dx = (x - cx) / rx
                dy = (y - cy) / ry
                if dx * dx + dy * dy <= 1.0:
                    self.pixels[y * WIDTH + x] = colour


def _fish_frame(step: int, rng: _Lcg, bubbles: list[tuple[int, int]]) -> bytearray:
    """One frame of a fish crossing the tank, bubbles drifting up."""

    canvas = _Canvas()
    canvas.fill_rect(0, HEIGHT - 8, WIDTH, 8, 1)  # the floor
    phase = step / FRAMES
    cx = 15 + (WIDTH - 30) * phase
    cy = HEIGHT / 2 + 6 * (1 if step % 2 else -1) * 0.5
    canvas.fill_ellipse(cx, cy, 13, 7, 2)
    # The tail flips with the frame parity, which is all the animation the
    # eye needs at this size.
    tail_x = cx - 13
    for i in range(7):
        width = 7 - i
        y0 = int(cy) - width // 2 + (1 if step % 2 else 0)
        canvas.fill_rect(int(tail_x) - i, y0, 1, max(1, width), 3)
    canvas.fill_ellipse(cx + 7, cy - 2, 1.5, 1.5, 0)  # the eye
    for bx, by in bubbles:
        y = (by - step * 3) % HEIGHT
        canvas.fill_ellipse(bx, y, 2, 2, 4)
    return canvas.pixels


def _pulse_frame(step: int, rng: _Lcg, stars: list[tuple[int, int]]) -> bytearray:
    """Concentric rings breathing out from the centre."""

    canvas = _Canvas()
    for sx, sy in stars:
        canvas.pixels[sy * WIDTH + sx] = 1
    phase = step / FRAMES
    for ring in range(3):
        radius = 6 + ((phase + ring / 3) % 1.0) * 34
        colour = 2 if ring % 2 == 0 else 3
        canvas.fill_ellipse(WIDTH / 2, HEIGHT / 2, radius, radius * 0.75, colour)
        canvas.fill_ellipse(WIDTH / 2, HEIGHT / 2, radius - 2.5, (radius - 2.5) * 0.75, 0)
    canvas.fill_ellipse(WIDTH / 2, HEIGHT / 2, 3, 3, 4)
    return canvas.pixels


_MOTIF_WORDS: dict[str, tuple[str, ...]] = {
    "fish": ("魚", "釣り", "さかな", "fish"),
    # C-1850: the pulse had no words of its own. It is the default AND one of
    # the two motifs, so 「パルスのGIFを作って」 matched nothing, came out as the
    # default - the very thing that was asked for - and was announced as
    # 「依頼に合う絵柄が無かった」. The picture was right and the sentence was a
    # lie. The words are the ones a person reaches for when naming this
    # picture: its label, the rings it draws, and the English the CLI shows.
    #
    # 「波」 is deliberately absent. 「波のGIF」 names a subject this generator
    # does not draw, and the honest note (C-1258) is the right answer there;
    # reading it as the pattern would claim the wave was drawn. 「脈打つ」 is
    # kept whole for the same class of reason - a bare 「脈」 would turn
    # 「山脈のGIF」 into a request for concentric rings.
    "pulse": ("パルス", "同心円", "波紋", "脈打つ", "pulse", "ripple"),
}

#: The motif used when a request names none. Named here so the honest note and
#: :func:`choose_motif` agree on which one that is.
DEFAULT_MOTIF = "pulse"

#: How each motif is named to the operator. The summary never named the motif
#: at all before C-1258; the reader saw 「アニメ GIF を作りました」 whether they
#: got their fish or the abstract default.
MOTIF_LABELS: dict[str, str] = {"fish": "魚", "pulse": "パルス（同心円）"}


def named_motif(request: str) -> str | None:
    """The motif a request explicitly asks for, or ``None`` if it names none.

    ``choose_motif`` collapses 「no match」 into the default, which is right for
    picking what to draw but hides the one fact the operator needs: that their
    words matched no motif. This returns ``None`` in that case so the caller
    can say so (C-1258).
    """

    text = unicodedata.normalize("NFKC", request).casefold()
    for motif, words in _MOTIF_WORDS.items():
        if any(word in text for word in words):
            return motif
    return None


def choose_motif(request: str) -> str:
    return named_motif(request) or DEFAULT_MOTIF


# ------------------------------------------------------------- encoding


def _pack_literals(indices: bytes) -> bytes:
    """LZW-pack pixel indices as literal codes only.

    A CLEAR goes out first and again before the decoder's growing dictionary
    would push the code width past 8 bits (it adds one entry per code after
    the first, starting at ``_END + 1``), so every code in the stream is
    exactly ``_MIN_CODE_SIZE + 1`` bits and the packer needs no dictionary
    at all.
    """

    width = _MIN_CODE_SIZE + 1
    room = (1 << width) - _END - 2  # codes before the width would grow
    out = bytearray()
    accumulator = 0
    bits = 0

    def emit(code: int) -> None:
        nonlocal accumulator, bits
        accumulator |= code << bits
        bits += width
        while bits >= 8:
            out.append(accumulator & 0xFF)
            accumulator >>= 8
            bits -= 8

    emit(_CLEAR)
    since_clear = 0
    for index in indices:
        if since_clear >= room:
            emit(_CLEAR)
            since_clear = 0
        emit(index)
        since_clear += 1
    emit(_END)
    if bits:
        out.append(accumulator & 0xFF)
    return bytes(out)


def _sub_blocks(payload: bytes) -> bytes:
    out = bytearray()
    for start in range(0, len(payload), 255):
        chunk = payload[start : start + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


def _gif_bytes(frames: list[bytearray]) -> bytes:
    out = bytearray()
    out += b"GIF89a"
    out += struct.pack("<HH", WIDTH, HEIGHT)
    # Global colour table present, 8 bits of colour resolution, table size
    # flag 6 -> 128 entries.
    out += bytes([0xF6, 0, 0])
    for r, g, b in PALETTE:
        out += bytes([r, g, b])
    out += bytes(3) * (_TABLE_SIZE - len(PALETTE))
    # NETSCAPE application extension: loop forever. The one extension worth
    # carrying, because without it "animated" means "plays once while you
    # look away".
    out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    for pixels in frames:
        out += b"\x21\xf9\x04\x04" + struct.pack("<H", DELAY_CS) + b"\x00\x00"
        out += b"\x2c" + struct.pack("<HHHH", 0, 0, WIDTH, HEIGHT) + b"\x00"
        out += bytes([_MIN_CODE_SIZE])
        out += _sub_blocks(_pack_literals(bytes(pixels)))
    out += b"\x3b"
    return bytes(out)


# ----------------------------------------------------------- generating


#: GIF-kind nouns a title should not end with, since the artifact already is
#: one: 「猫のGIF」→「猫」, 「鳥のアニメGIF」→「鳥」 (C-1265, the GIF twin of the
#: document C-1246 and deck C-1249). Longer spellings first so 「アニメGIF」 goes
#: whole; optional leading 「の」; applied once and only when a subject remains.
_TITLE_KIND_SUFFIX = re.compile(
    r"の?(?:アニメーション|アニメ画像|アニメgif|アニメ|gif|animation)$", re.IGNORECASE
)

#: The 「について/に関する」 phrase a request points its subject with, so
#: 「海に関するアニメGIF」 does not title 「海に関する」 (C-1485, the GIF twin of the
#: document C-1255). Anchored to the tail so a subject that merely contains it
#: mid-phrase is untouched.
_TITLE_ABOUT_SUFFIX = re.compile(r"(?:について(?:の)?|に関して(?:の)?|に関する)$")


def _title_from(request: str) -> str:
    stripped = re.split(r"を?(?:作って|作成して|生成して|つくって|出力して)", request)[0]
    # C-1829: without this 「魚のGIFを急いで作って」 titled itself 「魚のGIFを急い」 -
    # cut inside the okurigana - and kept the GIF the title must not echo.
    # C-1841: 「make a gif of a fish」 was the whole sentence until now.
    stripped = drop_english_frame(stripped)
    stripped = drop_request_adverbs(stripped)
    # C-1833: 「30フレームのGIFを作って」 was titled 「30フレーム」. The length note
    # (C-1823) reads the request, not the title, so it still says 10 フレーム.
    stripped = drop_size_phrases(stripped)
    stripped = re.sub(r"[をのはがにで]+$", "", stripped.strip()).strip()
    # The subject alone: 「猫のGIF」 says GIF in its title and again in the summary
    # 「…のアニメ GIF」 (C-1265). C-1485: peel the trailing particle, kind word and
    # about-phrase repeatedly - a request stacks two kind words (「猫のアニメーション
    # GIF」) or an about-phrase behind a kind word (「海に関するアニメGIF」), and
    # stripping each once left the inner word on the cover. Each pass only shrinks,
    # so the equality check terminates it; a bare 「GIFを作って」 keeps its default.
    peeled = stripped
    while True:
        step = re.sub(r"[をのはがにで]+$", "", peeled).strip()
        step = _TITLE_KIND_SUFFIX.sub("", step).strip()
        step = _TITLE_ABOUT_SUFFIX.sub("", step).strip()
        if step == peeled:
            break
        peeled = step
    if peeled:
        stripped = peeled
    return stripped[:60] or "アニメ画像"


def generate_gif(
    request: str,
    *,
    motif: str | None = None,
    seed: int | None = None,
    evidence: list[str] | None = None,
) -> GeneratedGif:
    """Build one looping animation from the request, deterministically."""

    # An explicit ``motif=`` is the caller naming it; a derived one is named
    # only when a word in the request matched (C-1258).
    derived = named_motif(request)
    chosen = motif or derived or DEFAULT_MOTIF
    named = motif is not None or derived is not None
    actual_seed = zlib.crc32(request.encode("utf-8")) if seed is None else seed
    rng = _Lcg(actual_seed)

    if chosen == "fish":
        bubbles = [(10 + rng.below(WIDTH - 20), rng.below(HEIGHT)) for _ in range(6)]
        frames = [_fish_frame(step, rng, bubbles) for step in range(FRAMES)]
    else:
        stars = [(rng.below(WIDTH), rng.below(HEIGHT)) for _ in range(24)]
        frames = [_pulse_frame(step, rng, stars) for step in range(FRAMES)]

    return GeneratedGif(
        title=_title_from(request),
        motif=chosen,
        seed=actual_seed,
        data=_gif_bytes(frames),
        motif_named=named,
        evidence=tuple(evidence or ()),
    )


def save_gif(gif: GeneratedGif, data_dir: str | Path) -> Path:
    """Write into the flat artifacts directory the browser already lists."""

    directory = Path(data_dir) / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = unique_path(directory, f"gif-{gif.motif}-{stamp}", ".gif")
    path.write_bytes(gif.data)
    return path


# ----------------------------------------------------------- validating


def parse_gif(data: bytes) -> dict:
    """Walk the actual blocks and report what the file really contains.

    This is the instrument behind ``creation_gif_generated``, so it trusts
    nothing: a file that claims frames it does not carry, ends without a
    trailer, or contains a block the walker does not recognise is reported
    broken exactly as a foreign decoder would find it.
    """

    failures: list[str] = []
    frames = 0
    looped = False
    if data[:6] != b"GIF89a":
        return {"valid": False, "frames": 0, "failures": ["not a GIF89a header"]}
    width, height = struct.unpack_from("<HH", data, 6)
    packed = data[10]
    pos = 13
    if packed & 0x80:
        pos += 3 * (2 << (packed & 0x07))

    def skip_sub_blocks(at: int) -> int:
        while at < len(data) and data[at]:
            at += 1 + data[at]
        return at + 1

    while pos < len(data):
        block = data[pos]
        if block == 0x3B:  # trailer
            pos += 1
            break
        if block == 0x21:  # extension
            if data[pos + 1 : pos + 2] == b"\xff" and b"NETSCAPE" in data[pos : pos + 16]:
                looped = True
            pos = skip_sub_blocks(pos + 2)
            continue
        if block == 0x2C:  # image descriptor
            local = data[pos + 9]
            pos += 10
            if local & 0x80:
                pos += 3 * (2 << (local & 0x07))
            pos += 1  # LZW minimum code size
            pos = skip_sub_blocks(pos)
            frames += 1
            continue
        failures.append(f"unknown block 0x{block:02x} at {pos}")
        break
    else:
        failures.append("no trailer byte")

    if width == 0 or height == 0:
        failures.append("zero dimensions")
    if frames < 2:
        failures.append(f"{frames} frame(s); an animation needs more than one")
    if not looped:
        failures.append("no NETSCAPE loop extension")
    if pos != len(data):
        failures.append(f"{len(data) - pos} unread byte(s) after the trailer")

    return {
        "valid": not failures,
        "frames": frames,
        "width": width,
        "height": height,
        "looped": looped,
        "bytes": len(data),
        "failures": failures,
    }


def validate_gif(gif: GeneratedGif) -> dict:
    return parse_gif(gif.data)


__all__ = [
    "DEFAULT_MOTIF",
    "DELAY_CS",
    "FRAMES",
    "length_note",
    "loop_seconds",
    "requested_frames",
    "requested_seconds",
    "GeneratedGif",
    "MOTIF_LABELS",
    "PALETTE",
    "choose_motif",
    "generate_gif",
    "named_motif",
    "parse_gif",
    "save_gif",
    "validate_gif",
]
