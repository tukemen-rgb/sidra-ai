"""The GIF moves forever and cannot be stopped. Why is that still safe?

It is safe, and this pins down the reasons - because they are conditions,
not properties, and a later change can break one of them without anyone
noticing. §6 already records that lesson from C-1892: "it matched the
measurement so nothing needs changing" is only true *under the conditions
it was measured in*, and unless those are written down the next person
cannot check them again.

Measured on the bytes of a generated GIF: 10 frames, 80ms each, NETSCAPE
repeat count 0 (forever), one cycle 0.80s, canvas 120x90. Every frame is
a different picture. Two standards could bite and neither does:

  * **2.3.1 Three Flashes (Level A, §15)** does not bite because of the
    small-area exemption - 120x90 is 10,800px, 12.4% of the ~341x256
    rectangle that subtends 10 degrees, against a limit of 25%. Widen the
    canvas and the exemption is gone.
  * **2.2.2 Pause, Stop, Hide (Level A)** does not bite because its third
    condition is not met: the animation is not "presented in parallel
    with other content". SIDRA hands the GIF over as an `image/gif`
    download and embeds it in none of its own pages. Put a preview in a
    file list and the Level A requirement fires that same day.

And a GIF cannot read `prefers-reduced-motion`. Every SIDRA page has a
switch that reduces motion (`creation_motion_switch`); the GIF is the one
artifact that moves and cannot be stilled. That is why the conditions are
worth guarding rather than shrugging at.

So this judge asserts the conditions, not the conclusion:

  (a) the canvas stays inside the area exemption, with the measured
      headroom reported rather than hidden;
  (b) one cycle stays at or under five seconds, which is the number G152
      works with (frames x frame time x repeats);
  (c) SIDRA embeds the GIF in none of its own HTML - checked by reading
      the source, because this is a claim about the product's surfaces
      and not about one generated file;
  (d) and the frames really differ, so "it animates" is not assumed.

None of these say the GIF ought to loop forever. They say that while it
does, these are the three things holding the roof up.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

#: The rectangle that subtends 10 degrees of the visual field at a typical
#: viewing distance, and the share of it a flashing area may occupy before
#: the exemption in 2.3.1 stops applying (§15 fact 2).
TEN_DEGREE_PX = 341 * 256
AREA_LIMIT = 0.25

#: G152 works to five seconds: frames x frame time x repeats.
CYCLE_LIMIT_S = 5.0

#: Requests to build from - both motifs the product has, so a motif cannot
#: be added without being measured.
REQUESTS: tuple[str, ...] = ("魚のGIFを作って", "波のGIFを作って")


@dataclass(frozen=True)
class GifMotionResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def read_gif(data: bytes) -> dict:
    """Frame count, per-frame delays, loop count and frame digests.

    Parsed out of the bytes rather than taken from the generator, so what
    is measured is the file an operator receives.
    """

    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    i = 13
    flags = data[10]
    if flags & 0x80:
        i += 3 * (2 ** ((flags & 7) + 1))
    delays: list[int] = []
    digests: list[str] = []
    loops: int | None = None
    while i < len(data):
        block = data[i]
        if block == 0x21:  # extension
            label = data[i + 1]
            size = data[i + 2]
            payload = data[i + 3:i + 3 + size]
            i += 3 + size
            subs: list[bytes] = []
            while data[i] != 0:
                n = data[i]
                subs.append(data[i + 1:i + 1 + n])
                i += n + 1
            i += 1
            if label == 0xF9 and size >= 4:
                delays.append(int.from_bytes(payload[1:3], "little"))
            elif label == 0xFF and payload[:11] == b"NETSCAPE2.0" and subs:
                loops = int.from_bytes(subs[0][1:3], "little")
        elif block == 0x2C:  # image descriptor
            local = data[i + 9]
            i += 10
            if local & 0x80:
                i += 3 * (2 ** ((local & 7) + 1))
            i += 1  # LZW minimum code size
            blob = bytearray()
            while data[i] != 0:
                n = data[i]
                blob += data[i + 1:i + 1 + n]
                i += n + 1
            i += 1
            digests.append(hashlib.sha256(bytes(blob)).hexdigest())
        elif block == 0x3B:  # trailer
            break
        else:
            i += 1
    return {
        "width": width,
        "height": height,
        "delays": delays,
        "loops": loops,
        "frames": len(digests),
        "distinct": len(set(digests)),
    }


def _embedded_in_any_page() -> list[str]:
    """Places SIDRA's own source puts a .gif into HTML it serves.

    A grep rather than a parse, deliberately: the claim being guarded is
    "nothing embeds it", and the cheapest honest way to break that claim
    is to find any markup that would. Only the shipped package is read.
    """

    root = Path(__file__).resolve().parents[1]
    marker = re.compile(r"""<img[^>]*\.gif|url\(\s*['"]?[^)'"]*\.gif""", re.I)
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.parts[-2:] == ("evals",):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if marker.search(text):
            found.append(str(path.relative_to(root)))
    return found


def evaluate_gif_motion_stays_within_the_exemption() -> GifMotionResult:
    from sidra_ai.creation.gifs import MOTIF_LABELS, generate_gif

    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    built = [(request, read_gif(generate_gif(request).data)) for request in REQUESTS]

    # The table has to reach every motif the product offers, or a motif can
    # be added with a bigger canvas and nobody measures it.
    motifs = {generate_gif(request).motif for request in REQUESTS}
    if motifs != set(MOTIF_LABELS):
        failures.append(
            f"the requests cover motifs {sorted(motifs)} but the product "
            f"offers {sorted(MOTIF_LABELS)}"
        )
    else:
        checks += 1

    # (c) nothing in the product embeds a GIF in a page it serves
    embedded = _embedded_in_any_page()
    if embedded:
        failures.append(
            "a .gif is embedded in HTML the product serves ("
            + "、".join(embedded[:3])
            + ") - 2.2.2 Pause, Stop, Hide (Level A) now applies, because the "
            "animation is presented in parallel with other content"
        )
    else:
        checks += 1

    for request, gif in built:
        area = gif["width"] * gif["height"]
        share = area / TEN_DEGREE_PX

        # (a) inside the area exemption
        if share > AREA_LIMIT:
            failures.append(
                f"{request}: {gif['width']}x{gif['height']} is {share:.1%} of the "
                f"10-degree rectangle, past the {AREA_LIMIT:.0%} exemption - the "
                "flash limit in 2.3.1 now applies to it"
            )
        else:
            checks += 1

        # (b) one cycle within the five seconds G152 works to
        cycle = sum(gif["delays"]) / 100.0
        if not gif["delays"]:
            failures.append(f"{request}: the file declares no frame delays at all")
        elif cycle > CYCLE_LIMIT_S:
            failures.append(
                f"{request}: one cycle is {cycle:.2f}s, past the {CYCLE_LIMIT_S:.0f}s "
                "G152 works to - and it repeats "
                + ("forever" if gif["loops"] == 0 else f"{gif['loops']} times")
            )
        else:
            checks += 1

        # (d) and it really animates
        if gif["frames"] < 2 or gif["distinct"] < gif["frames"]:
            failures.append(
                f"{request}: {gif['frames']} frames but only {gif['distinct']} "
                "distinct - the same picture repeated is not an animation"
            )
        else:
            checks += 1

        readings.append(
            f"{request} {gif['width']}×{gif['height']}（免除の {share:.1%}）"
            f"・{gif['frames']}コマ全部別・1周 {cycle:.2f}s"
            f"・繰り返し{'無限' if gif['loops'] == 0 else gif['loops']}"
        )

    return GifMotionResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )
