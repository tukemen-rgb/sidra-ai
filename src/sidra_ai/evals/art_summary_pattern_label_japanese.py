"""Does the art summary name its pattern in Japanese, not the internal key?

C-1619. The art summary led with 「パターン: {art.pattern}」, printing the raw
pattern key - `flow` / `orbits` - on a Japanese page. 3D says 「形状: 魚」 and
GIF says 「絵柄: 魚」 (Japanese labels), and this summary's own default note
already says 「既定の『フロー』」, so a single reply showed both `flow` and
フロー for one pattern; a named pattern showed only the English key, with no
Japanese label anywhere. C-1259 fixed the same class for the game subtitle
(「テンプレート <key>」 → 「ジャンル <日本語>」).

The summary now uses PATTERN_LABELS, so 「パターン: 軌道」/「パターン: フロー」.
The default-pattern disclosure (C-1256), the colour note (C-1271), the seed and
the determinism line are unchanged.

Measured through the real chat path: the summary is the answer a user reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_DEFAULT_DISCLOSURE = "指定できるパターンは フロー / 軌道 です"
_COLOR_NOTE = "依頼にあった色は今の配色に反映していません"
_DETERMINISM = "同じ依頼なら同じ絵"


@dataclass(frozen=True)
class ArtPatternLabelResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="art-label-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer(service, request: str) -> str:
    return str((service.chat(request) or {}).get("answer") or "")


def evaluate_art_summary_pattern_label_japanese() -> ArtPatternLabelResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- a named pattern shows the Japanese label, not the English key ---
    orbit = _answer(service, "軌道のアートを作って")
    add("パターン: 軌道" in orbit, f"orbit pattern not labelled 軌道: 「{orbit}」")
    add("orbits" not in orbit, f"the internal key 'orbits' leaked: 「{orbit}」")

    flow = _answer(service, "フローのアートを作って")
    add("パターン: フロー" in flow, f"flow pattern not labelled フロー: 「{flow}」")
    add("flow" not in flow, f"the internal key 'flow' leaked: 「{flow}」")

    # --- the default (unnamed) path labels the default in Japanese too ---
    default = _answer(service, "螺旋のアートを作って")
    add("パターン: フロー" in default, f"default pattern not labelled フロー: 「{default}」")
    add("flow" not in default, f"the internal key 'flow' leaked on default: 「{default}」")
    add(_DEFAULT_DISCLOSURE in default, "the default-pattern disclosure was lost")

    # --- non-regression: seed, determinism, colour note ---
    add("seed" in orbit, "the seed line went missing")
    add(_DETERMINISM in orbit, "the determinism line went missing")
    colored = _answer(service, "青い螺旋のアートを作って")
    add(_COLOR_NOTE in colored, "the colour-not-applied note went missing")

    total = 10
    return ArtPatternLabelResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "ArtPatternLabelResult",
    "evaluate_art_summary_pattern_label_japanese",
]
