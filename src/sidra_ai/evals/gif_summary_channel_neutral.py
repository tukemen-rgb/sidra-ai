"""Does the GIF summary avoid Web-UI-only navigation a CLI reader can't follow?

C-1610. Every creation generator's summary is read in two places - the web
page's file list and ``sidra-ask`` in a terminal - so it must describe the
artifact in a way that fits both. Art says 「HTML をブラウザで開くと」, a game
says 「ブラウザで開けばそのまま遊べます」, a 3D model says 「.obj は…で開けます」:
each tells the reader to open the file, and each channel surfaces where it is
(the web list, or the CLI's 「生成ファイル:」 line). The GIF summary alone said
「生成ファイル一覧からダウンロードして…」 - it points at the web UI's file list,
which does not exist in a terminal, so a CLI reader is sent to a list that is
not there.

The fix drops the web-only navigation and keeps the channel-neutral 「ブラウザや
画像ビューアーで開けます。」 (a GIF, unlike an HTML page, is opened in a viewer, so
that guidance stays). The default-motif disclosure (C-1258) and the colour note
(C-1272) are unchanged.

Measured through the real ``chat`` path: the summary is the answer a user reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The web-only navigation no summary should carry: it names a UI element the
#: CLI does not have.
_WEB_ONLY_MARKER = "生成ファイル一覧"

#: A GIF is opened in a viewer, so the summary must still say how.
_OPEN_HINT = "ブラウザ"

#: The default-motif disclosure that must survive the wording change (C-1258).
_DEFAULT_NOTE = "依頼に合う絵柄が無かったので"
_MOTIF_LABEL = "絵柄"

#: One request per generator, to prove the GIF was the only offender and stays
#: consistent with the rest.
_GIF_REQUESTS = ("魚のGIFを作って", "GIFを作って")
_OTHER_REQUESTS = (
    "螺旋のアートを作って",
    "レースゲームを作って",
    "舟の3Dモデルを作って",
    "提案スライドを作って",
)


@dataclass(frozen=True)
class GifSummaryChannelNeutralResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _build_service():
    import tempfile

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings

    tmp = Path(tempfile.mkdtemp(prefix="gif-channel-"))
    return SidraService(Settings(data_dir=str(tmp / "sidra")))


def _answer_of(service, request: str) -> str:
    result = service.chat(request) or {}
    return str(result.get("answer") or "")


def evaluate_gif_summary_channel_neutral() -> GifSummaryChannelNeutralResult:
    service = _build_service()
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- the GIF summary: no web-only navigation, but still says how to open ---
    for request in _GIF_REQUESTS:
        answer = _answer_of(service, request)
        add(_WEB_ONLY_MARKER not in answer,
            f"{request!r}: summary still points at 「{_WEB_ONLY_MARKER}」: 「{answer}」")
        add(_OPEN_HINT in answer,
            f"{request!r}: summary no longer says how to open the GIF: 「{answer}」")

    # --- the other generators never had it, and must not grow it ---
    for request in _OTHER_REQUESTS:
        answer = _answer_of(service, request)
        add(_WEB_ONLY_MARKER not in answer,
            f"{request!r}: a non-GIF summary references 「{_WEB_ONLY_MARKER}」: 「{answer}」")

    # --- non-regression: the unnamed-motif GIF still discloses the default ---
    unnamed = _answer_of(service, "GIFを作って")
    add(_DEFAULT_NOTE in unnamed,
        f"the default-motif disclosure was lost: 「{unnamed}」")
    add(_MOTIF_LABEL in unnamed,
        f"the summary no longer names the motif: 「{unnamed}」")

    total = 2 * len(_GIF_REQUESTS) + len(_OTHER_REQUESTS) + 2
    return GifSummaryChannelNeutralResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = [
    "GifSummaryChannelNeutralResult",
    "evaluate_gif_summary_channel_neutral",
]
