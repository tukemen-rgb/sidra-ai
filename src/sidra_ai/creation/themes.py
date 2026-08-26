"""Named palettes a generated artifact can be asked for.

The default is GAMEYARD's own palette and stays that way. Themes exist for
the request that says so - 「紙のテーマで」 - and for nothing else, because a
generator that quietly redecorated every artifact would have changed the
product's identity while appearing to add a feature. So the default theme's
tokens are *derived from* :data:`sidra_ai.creation.games.GAMEYARD_TOKENS`
rather than retyped: the site's DESIGN.md remains the one source, and a theme
switch cannot drift the default away from it.

Two properties are worth more than the count of themes.

The first is that **a theme has to be readable**. Colours picked by eye pass
"three themes exist" and fail the person reading the slide, so every theme is
checked against WCAG contrast ratios here, and a theme that cannot clear them
is not a theme. The floors are deliberately at the strict end: body text is
held to AAA (7:1) because these artifacts are read as documents, and the
accent colours to the 3:1 that non-text UI needs.

The second is that **not naming a theme changes nothing**. That direction is
easy to lose and is the one the metric would not notice on its own: a themed
generator whose "default" drifted by one hex digit still measures as three
working themes.

No model decides this. The mapping from words to a theme is a table, so the
same request produces the same palette on the echo backend.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

#: Straight from site ``docs/DESIGN.md`` §2. Duplicated as data rather than
#: prose so a template cannot drift from the identity without this changing.
#: It lives here, and :mod:`sidra_ai.creation.games` re-exports it, because
#: the default theme must be built *from* these values: two hand-kept copies
#: would let the default drift from the site while every test still passed.
GAMEYARD_TOKENS = {
    "bg": "#05070f",
    "surface": "#0a0f1c",
    "raised": "#0c1322",
    "cyan": "#2ee6ff",
    "magenta": "#ff5cc8",
    "radius": "12px",
    "radius_tight": "8px",
}

#: Every slot a template may colour. Kept as an explicit tuple so a theme
#: that forgot one fails at import time rather than rendering a page with a
#: literal ``None`` in its stylesheet.
TOKEN_KEYS: tuple[str, ...] = (
    "scheme",  # the CSS `color-scheme` keyword, so form controls match
    "bg",
    "surface",
    "raised",
    "border",
    "text",  # body copy
    "subtle",  # taglines and secondary lines
    "code",  # the monospace how-to-play block
    "muted",  # sources and footers
    "accent",
    "alert",
    "radius",
    "radius_tight",
)

#: Contrast floors, as ``(foreground, background, minimum ratio)``.
#:
#: Body text is held to WCAG AAA (7:1) rather than AA: a deck or a game page
#: is read, not glanced at. ``muted`` carries source lines, which are small
#: but still text, so it keeps the AA 4.5:1. The accents are drawn shapes and
#: headings, which need the 3:1 that non-text contrast asks for.
CONTRAST_FLOORS: tuple[tuple[str, str, float], ...] = (
    ("text", "bg", 7.0),
    ("text", "surface", 7.0),
    ("code", "raised", 7.0),
    ("subtle", "bg", 4.5),
    ("muted", "surface", 4.5),
    ("accent", "surface", 3.0),
    ("alert", "surface", 3.0),
)


@dataclass(frozen=True)
class Theme:
    """One palette, and the words that ask for it.

    ``words`` are matched only alongside the word テーマ / theme - see
    :func:`select_theme`. A message that happens to mention 紙 is not a
    request for the paper palette.
    """

    key: str
    label: str
    words: tuple[str, ...]
    tokens: dict[str, str]


_GAMEYARD_TOKENS: dict[str, str] = {
    "scheme": "dark",
    "bg": GAMEYARD_TOKENS["bg"],
    "surface": GAMEYARD_TOKENS["surface"],
    "raised": GAMEYARD_TOKENS["raised"],
    "border": "#16243a",
    "text": "#dfe7f5",
    "subtle": "#9fb0c8",
    "code": "#c3d2e6",
    "muted": "#7d8ea6",
    "accent": GAMEYARD_TOKENS["cyan"],
    "alert": GAMEYARD_TOKENS["magenta"],
    "radius": GAMEYARD_TOKENS["radius"],
    "radius_tight": GAMEYARD_TOKENS["radius_tight"],
}

#: The default first. Order is the order a tie is broken in and the order the
#: catalogue is reported in.
THEMES: dict[str, Theme] = {
    "gameyard": Theme(
        key="gameyard",
        label="GAMEYARD（既定）",
        words=("gameyard", "ゲームヤード", "既定", "標準", "デフォルト"),
        tokens=dict(_GAMEYARD_TOKENS),
    ),
    "paper": Theme(
        key="paper",
        label="紙（印刷・投影向け）",
        words=("紙", "ペーパー", "paper", "印刷", "白", "light"),
        tokens={
            "scheme": "light",
            "bg": "#ffffff",
            "surface": "#f5f7fb",
            "raised": "#eceff7",
            "border": "#d3d9e6",
            "text": "#11151d",
            "subtle": "#414b5c",
            "code": "#1d2531",
            "muted": "#4d5768",
            "accent": "#0b5c72",
            "alert": "#9c1462",
            "radius": GAMEYARD_TOKENS["radius"],
            "radius_tight": GAMEYARD_TOKENS["radius_tight"],
        },
    ),
    "terminal": Theme(
        key="terminal",
        label="ターミナル（緑単色）",
        words=("ターミナル", "端末", "terminal", "コンソール", "緑"),
        tokens={
            "scheme": "dark",
            "bg": "#000000",
            "surface": "#061006",
            "raised": "#0a1a0a",
            "border": "#134013",
            "text": "#d6ffd6",
            "subtle": "#8fdc8f",
            "code": "#bdf5bd",
            "muted": "#74c274",
            "accent": "#2bff6b",
            "alert": "#ffd23f",
            "radius": "4px",
            "radius_tight": "2px",
        },
    ),
    "dusk": Theme(
        key="dusk",
        label="夕暮れ（紫と橙）",
        words=("夕暮れ", "夕焼け", "サンセット", "dusk", "sunset", "紫", "暖色"),
        tokens={
            "scheme": "dark",
            "bg": "#130a1c",
            "surface": "#1c1028",
            "raised": "#251636",
            "border": "#3b2452",
            "text": "#f4e8ff",
            "subtle": "#c2a8dc",
            "code": "#ddcaef",
            "muted": "#a288bd",
            "accent": "#ffb454",
            "alert": "#ff6ea9",
            "radius": "10px",
            "radius_tight": "6px",
        },
    ),
}

DEFAULT_THEME = THEMES["gameyard"]

#: The cue that turns a colour word into a theme request. Without it, 「紙の
#: 資料を作って」 would silently come out white - the word names the subject,
#: not the palette.
_THEME_CUES: tuple[str, ...] = ("テーマ", "theme", "配色", "カラー")


def _luminance(colour: str) -> float:
    """WCAG relative luminance of a ``#rrggbb`` string."""

    value = colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio, 1.0 (identical) to 21.0 (black on white)."""

    a, b = _luminance(foreground), _luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def validate_theme(theme: Theme) -> dict[str, object]:
    """Every token present, and every pairing readable.

    Returns the failures rather than raising: the caller reports them, and a
    theme that fails is dropped from the catalogue the metric counts instead
    of taking the whole generator down.
    """

    failures: list[str] = []
    missing = [key for key in TOKEN_KEYS if key not in theme.tokens]
    failures += [f"token 欠落: {key}" for key in missing]

    ratios: dict[str, float] = {}
    for fg, bg, floor in CONTRAST_FLOORS:
        if fg in missing or bg in missing:
            continue
        ratio = contrast_ratio(theme.tokens[fg], theme.tokens[bg])
        ratios[f"{fg}/{bg}"] = round(ratio, 2)
        if ratio < floor:
            failures.append(f"{fg}/{bg} のコントラスト {ratio:.2f} < {floor}")

    return {"key": theme.key, "readable": not failures, "failures": failures, "ratios": ratios}


def select_theme(message: str) -> Theme:
    """Pick the theme a message asks for, or the default.

    Requires both a theme cue (テーマ / 配色 / theme) and one of the theme's
    own words, for the same reason
    :func:`sidra_ai.creation.intent.detect_creation_intent` requires both a
    verb and an artifact: one signal alone reads ordinary subject matter as
    an instruction. Ties go to the word sitting latest in the message.
    """

    text = unicodedata.normalize("NFKC", message).casefold()
    if not any(cue in text for cue in _THEME_CUES):
        return DEFAULT_THEME

    best: tuple[int, Theme] | None = None
    for theme in THEMES.values():
        for word in theme.words:
            index = text.rfind(word.casefold())
            if index >= 0 and (best is None or index > best[0]):
                best = (index, theme)
    return DEFAULT_THEME if best is None else best[1]


def readable_themes() -> tuple[str, ...]:
    """Keys of the themes that clear :data:`CONTRAST_FLOORS`."""

    return tuple(key for key, theme in THEMES.items() if validate_theme(theme)["readable"])


__all__ = [
    "CONTRAST_FLOORS",
    "GAMEYARD_TOKENS",
    "DEFAULT_THEME",
    "THEMES",
    "TOKEN_KEYS",
    "Theme",
    "contrast_ratio",
    "readable_themes",
    "select_theme",
    "validate_theme",
]
