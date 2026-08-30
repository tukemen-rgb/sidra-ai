"""Shrink a local video so the whole thing fits through the chat upload cap.

Written for the owner's Windows machine and for one job: a video too large
to attach (measured: 150MB refused) needs every minute of it, motion
included, to reach the assistant. Frames alone lose the motion; a clip
loses the rest. So the whole file is re-encoded small (480p is plenty for
studying movement - both reference videos that produced game templates were
phone screen recordings), and split into numbered parts only if the result
still exceeds a safe attachment size.

Run it on the owner's PC (Python 3.11+, no manual pasting of code - this
file arrives with ``git pull``)::

    py scripts\\shrink_video.py
    py scripts\\shrink_video.py "D:\\somewhere\\else"

The only dependency, imageio-ffmpeg (BSD, bundles a static ffmpeg), is
installed automatically. Output lands on the Desktop as ``sidra-small.mp4``
or ``sidra-part00.mp4`` onward. Nothing is uploaded by this script; the
owner attaches the files by hand, which is the point - the machine's files
leave it only through a person's explicit action.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

#: Conservative per-file target. A 15MB attachment is known to have gone
#: through; the cap itself is unknown, so parts aim below the proven size.
PART_MB = 13

VIDEO_PATTERNS = (
    "*.mp4", "*.mkv", "*.avi", "*.mov", "*.vob", "*.m2ts", "*.wmv", "*.mpg",
)


def find_largest_video(folder: str) -> str | None:
    hits: list[str] = []
    for pattern in VIDEO_PATTERNS:
        hits += glob.glob(os.path.join(folder, pattern))
        hits += glob.glob(os.path.join(folder, "**", pattern), recursive=True)
    hits = sorted(set(hits))
    if not hits:
        return None
    return max(hits, key=os.path.getsize)


def duration_of(ff: str, path: str) -> float:
    probe = subprocess.run([ff, "-i", path], capture_output=True, text=True, errors="ignore")
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if not match:
        raise SystemExit("動画の長さが読めませんでした: " + path)
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def main() -> int:
    print("準備中（初回だけ ffmpeg を取得します）…")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "imageio-ffmpeg"]
    )
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()

    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        os.path.join("~", "Videos", "Rip DVD App")
    )
    if os.path.isfile(target):
        # A file argument picks that exact video - the folder scan takes the
        # *largest* file, and a folder of DVD titles can hold several.
        source = target
    elif os.path.isdir(target):
        source = find_largest_video(target)
        if source is None:
            print("このフォルダに動画ファイルが見つかりません:", target)
            return 1
    else:
        print("見つかりません:", target)
        print('使い方: py scripts\\shrink_video.py "フォルダまたは動画ファイルのパス"')
        return 1
    print(f"対象: {source} ({os.path.getsize(source) // 1048576} MB)")

    # Next to the source, never the Desktop: on OneDrive-managed Windows
    # ``~\Desktop`` does not exist and ffmpeg dies on the output path -
    # measured on the owner's machine before this was changed.
    out_dir = os.path.join(os.path.dirname(source), "sidra-out")
    os.makedirs(out_dir, exist_ok=True)
    small = os.path.join(out_dir, "sidra-small.mp4")
    print("全編を 480p に再圧縮しています。下に time= が進んでいれば動いています…")
    subprocess.run(
        [
            ff, "-hide_banner", "-loglevel", "error", "-stats",
            "-i", source,
            "-vf", "scale=480:-2",
            "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "64k",
            small, "-y",
        ],
        check=True,
    )
    size_mb = os.path.getsize(small) / 1048576
    print(f"圧縮結果: {size_mb:.0f} MB")

    if size_mb <= PART_MB:
        print("1 本に収まりました。これをチャットに添付してください:")
        print("  " + small)
        return 0

    total = duration_of(ff, small)
    segment = max(30, int(total * PART_MB / size_mb))
    pattern = os.path.join(out_dir, "sidra-part%02d.mp4")
    subprocess.run(
        [
            ff, "-hide_banner", "-loglevel", "error",
            "-i", small, "-c", "copy",
            "-f", "segment", "-segment_time", str(segment),
            "-reset_timestamps", "1",
            pattern, "-y",
        ],
        check=True,
    )
    parts = sorted(glob.glob(os.path.join(out_dir, "sidra-part*.mp4")))
    print(f"{len(parts)} 本に分割しました。番号順に全部チャットへ添付してください:")
    for part in parts:
        print(f"  {part}  ({os.path.getsize(part) / 1048576:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
