"""Does a GIF title peel *stacked* kind words and the about-phrase, not just one?

C-1485, the GIF follow-through to the document C-1467 (repeated peel) and C-1255
(about-phrase). ``gifs._title_from`` stripped a trailing kind word exactly once
and never the 「について/に関する」 phrase, so a request that stacks two kind words
or hides one behind an about-phrase kept the inner word on the cover:

* 「猫のGIFアニメを作って」 → 「猫のGIF」 (the kind word GIF is left in the title,
  which then reads 「『猫のGIF』のアニメ GIF を作りました」 in the summary);
* 「猫のアニメーションGIFを作って」 → 「猫のアニメーション」;
* 「海に関するアニメGIFを作って」 → 「海に関する」 (the about-phrase survives).

The existing ``art_gif_title_no_kind_echo`` (C-1265) only covers a single trailing
kind word. This eval drives the real ``_title_from`` and reads the title.
"""

from __future__ import annotations

from dataclasses import dataclass

# Stacked kind words, or a kind word behind an about-phrase: the title must peel
# down to the subject alone, never leave a GIF-kind word or 「について/に関する」.
_STRIP = (
    ("猫のGIFアニメを作って", "猫"),
    ("猫のアニメーションGIFを作って", "猫"),
    ("海に関するアニメGIFを作って", "海"),
    ("猫についてのGIFを作って", "猫"),
    ("魚が泳ぐアニメについてのGIFを作って", "魚が泳ぐ"),
)

# Already correct - must stay correct (a single kind word, a subject that merely
# begins with アニメ, and the bare-kind fallback title).
_KEEP = (
    ("猫のGIFを作って", "猫"),
    ("泳ぐ魚のアニメGIFを作って", "泳ぐ魚"),
    ("アニメ制作のGIFを作って", "アニメ制作"),
    ("光る星のアニメーションを作って", "光る星"),
    ("GIFを作って", "GIF"),
)


@dataclass(frozen=True)
class GifTitleResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_gif_title_drops_stacked_kind_and_about() -> GifTitleResult:
    from sidra_ai.creation.gifs import _title_from

    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for request, expected in (*_STRIP, *_KEEP):
        title = _title_from(request)
        add(title == expected,
            f"title {title!r} != {expected!r} for {request!r}")

    total = len(_STRIP) + len(_KEEP)
    return GifTitleResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["GifTitleResult", "evaluate_gif_title_drops_stacked_kind_and_about"]
