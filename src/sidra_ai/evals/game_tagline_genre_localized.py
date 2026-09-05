"""Does a generated game's subtitle name its genre in Japanese, not the key?

C-1259: playing the ten templates in a browser (no JS errors) showed every
page's subtitle reading 「難易度 normal / テンプレート fishing」 - the internal
template key, in English, on a Japanese page. 「レースゲームを作って」 printed
「テンプレート racing」. The key is an implementation detail and the one English
word in the whole UI.

The subtitle now reads 「難易度 X / ジャンル <日本語>」, the label taken from the
genre vocabulary the router already shares. Checked on the real generated HTML
for every buildable template: the Japanese genre label is present and the
「テンプレート <key>」 leak is gone, while 「難易度 X」 (which tests pin) stays.
"""

from __future__ import annotations

from dataclasses import dataclass


def _labels() -> dict[str, str]:
    """Buildable template key -> its Japanese genre label."""

    from sidra_ai.creation.games import TEMPLATES
    from sidra_ai.creation.vocabulary import GENRES

    labels: dict[str, str] = {}
    for label, key, _words in GENRES:
        if key in TEMPLATES and key not in labels:
            labels[key] = label
    return labels


@dataclass(frozen=True)
class GameTaglineGenreResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_game_tagline_genre_localized() -> GameTaglineGenreResult:
    from sidra_ai.creation.games import TEMPLATES, generate_game

    labels = _labels()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    for key in TEMPLATES:
        label = labels.get(key)
        if label is None:
            failures.append(f"{key}: no Japanese genre label in the vocabulary")
            failures.append(f"{key}: (leak check skipped - no label)")
            continue
        # A real generation, pinned to this template, with a natural request.
        html = generate_game(f"{label}のゲームを作って", template=key).html
        # 1: the subtitle names the genre in Japanese.
        add(f"ジャンル {label}" in html,
            f"{key}: subtitle missing 「ジャンル {label}」")
        # 2: the English template key is no longer leaked as a template line.
        add(f"テンプレート {key}" not in html,
            f"{key}: still leaks 「テンプレート {key}」")

    total = 2 * len(TEMPLATES)
    return GameTaglineGenreResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["GameTaglineGenreResult", "evaluate_game_tagline_genre_localized"]
