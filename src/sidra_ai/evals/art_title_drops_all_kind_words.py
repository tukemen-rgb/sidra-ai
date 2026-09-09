"""Does the art title strip every ART kind word, not just アート/art?

C-1604. The intent detector routes every ART cue to the art generator - C-1480
added 壁紙/wallpaper/artwork/abstract art/digital art/生成アート alongside アート -
but ``_TITLE_KIND_SUFFIX`` stripped only アート/art/generative art. So
「猫の壁紙」 kept 壁紙 and 「海の生成アート」 lost only アート to a broken 「海の生成」,
echoing the kind in the summary the way C-1265/1246/1249/1485 fixed elsewhere.
The suffix now matches the cue set; a bare kind word still stands as its own
title.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtTitleKindResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_art_title_drops_all_kind_words() -> ArtTitleKindResult:
    from sidra_ai.creation.art import _title_from

    checks = 0
    failures: list[str] = []

    def check(request: str, expected: str) -> None:
        nonlocal checks
        got = _title_from(request)
        if got == expected:
            checks += 1
        else:
            failures.append(f"{request!r} -> {got!r}, expected {expected!r}")

    # STRIP: a kind word after a subject leaves the subject alone, and a
    # partial strip (生成アート -> 生成) no longer happens.
    check("猫の壁紙を作って", "猫")
    check("海の生成アートを作って", "海")
    check("猫のdigital artを作って", "猫")
    check("森のabstract artを作って", "森")
    check("夕焼けのwallpaperを作って", "夕焼け")
    check("犬のartworkを作って", "犬")

    # KEEP: patterns that are the subject, and a subject with no kind word,
    # are unchanged (non-regression against C-1265).
    check("螺旋のアートを作って", "螺旋")
    check("幾何学模様のアートを作って", "幾何学模様")
    check("夕焼けを作って", "夕焼け")
    # A bare kind word remains its own title (the C-1256 default, not blanked).
    nonlocal_ok = bool(_title_from("アートを作って").strip())
    if nonlocal_ok:
        checks += 1
    else:
        failures.append("bare 「アートを作って」 lost its title")

    total = 10
    return ArtTitleKindResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ArtTitleKindResult", "evaluate_art_title_drops_all_kind_words"]
