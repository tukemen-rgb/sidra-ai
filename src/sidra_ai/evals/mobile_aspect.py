"""Does a generated canvas keep its shape on a phone-width screen?

C-1204: the shared game shell styled the canvas ``width:100%;height:320px``.
Desktop content width is exactly 720px, so the 720x320 bitmap rendered 1:1
and looked perfect; at 352px of phone width the same rule squashed every
game 2x horizontally - ship a sliver, circles into tall ellipses, on-screen
touch buttons twice their intended height. All ten templates share the one
shell, so all ten were distorted; the 3D preview had the same class of bug
via ``max-width:100%`` with no height rule.

CSS layout cannot be computed offline, but the failure is fully decided by
two strings in the artifact: the canvas element's intrinsic ``width``/
``height`` attributes, and the ``canvas{...}`` style rule. A rule that
scales width while pinning height in pixels distorts at any width other
than the intrinsic one; ``height:auto`` (art.py's rule from day one)
preserves the intrinsic ratio everywhere. Each surface below is checked for
exactly that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CANVAS_TAG = re.compile(r"<canvas[^>]*width=\"(\d+)\"[^>]*height=\"(\d+)\"")
_CANVAS_RULE = re.compile(r"canvas\s*\{([^}]*)\}")
_PIXEL_HEIGHT = re.compile(r"(?<![-\w])height\s*:\s*\d+px")
_SCALED_WIDTH = re.compile(r"(?:max-)?width\s*:\s*100%")
_AUTO_HEIGHT = re.compile(r"height\s*:\s*auto")


@dataclass(frozen=True)
class MobileAspectResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def page_keeps_aspect(html: str) -> tuple[bool, str]:
    """Whether this artifact's canvas CSS preserves the intrinsic ratio."""

    if not _CANVAS_TAG.search(html):
        return False, "no sized <canvas> found"
    rule = _CANVAS_RULE.search(html)
    if rule is None:
        # No canvas rule at all: the element renders at its attribute size,
        # which overflows a phone but does not distort. Distortion is the
        # failure this eval exists for, overflow is a lesser, visible one.
        return True, "no canvas rule (attribute size)"
    body = rule.group(1)
    if not _SCALED_WIDTH.search(body):
        return True, "width not scaled; attribute size"
    if _PIXEL_HEIGHT.search(body):
        return False, "width scales but height is pinned in px (distorts)"
    ratio = re.search(r"aspect-ratio\s*:\s*([\d.]+)\s*/\s*([\d.]+)", body)
    if ratio is not None:
        tag = _CANVAS_TAG.search(html)
        declared = float(ratio.group(1)) / float(ratio.group(2))
        intrinsic = int(tag.group(1)) / int(tag.group(2))
        if abs(declared - intrinsic) > 0.01:
            return False, "aspect-ratio disagrees with the canvas attributes"
        return True, "width:100% with matching aspect-ratio"
    if not _AUTO_HEIGHT.search(body):
        return False, "width scales with no height rule (distorts)"
    return True, "width:100% with height:auto"


def evaluate_mobile_aspect() -> MobileAspectResult:
    from sidra_ai.creation.art import generate_art
    from sidra_ai.creation.games import generate_game
    from sidra_ai.creation.models3d import generate_model3d

    surfaces = (
        ("game", generate_game("シューティングゲームを作って").html),
        ("model3d", generate_model3d("魚の3Dモデルを作って").preview_html),
        ("art", generate_art("星空のアートを作って").html),
    )

    checks = 0
    failures: list[str] = []
    for name, html in surfaces:
        ok, reason = page_keeps_aspect(html)
        if ok:
            checks += 1
        else:
            failures.append(f"{name}: {reason}")

    return MobileAspectResult(
        passed=not failures, checks_passed=checks, checks_total=len(surfaces),
        failures=tuple(failures),
    )
