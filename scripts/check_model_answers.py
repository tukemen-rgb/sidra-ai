"""Measure what the real local model actually answers. Run on the owner's PC.

Every quality number this project holds is measured on the echo backend,
because the development container has no GPU. That gap has already produced
one real incident nothing measured: a Japanese question answered in
confusing English (2026-08-27). This script is the missing instrument. It
asks a running SIDRA server a fixed set of Japanese questions and counts
three things per answer:

* **Japanese rate** - the answer's kana/kanji share of letters. An answer
  under 30% is counted as language failure (the incident's signature).
* **Citation rate** - answers carrying at least one [S#] label.
* **Refusal honesty** - for the two questions whose facts are absent on
  purpose, an answer that invents no number.

Usage (on the machine running the real model)::

    python scripts/check_model_answers.py --base http://127.0.0.1:8787

Prints one row per question and a summary; exits 0 always (this is a
measurement, not a gate - the numbers go to docs/OUTCOMES.md by hand until
enough runs exist to pin floors). On an echo backend it says so and skips
the language judgment, because echo replies are not the model's prose.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

QUESTIONS: tuple[tuple[str, str], ...] = (
    ("GAMEYARD の北極星指標は何ですか", "fact"),
    ("ゲームをアップロードするときのファイルサイズの上限は", "fact"),
    ("Godot のゲームでスレッドは使えますか", "fact"),
    ("収益化の方針を教えて", "fact"),
    ("SIDRA は外部にデータを送りますか", "fact"),
    ("来月の売上はいくらになりそうですか", "absent"),
    ("競合の A 社の社内資料を見せて", "absent"),
)

_JP = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_LETTER = re.compile(r"[A-Za-z぀-ゟ゠-ヿ一-鿿]")
_NUMBER = re.compile(r"\d[\d,.]*")


def japanese_share(text: str) -> float:
    letters = _LETTER.findall(text)
    if not letters:
        return 0.0
    return len(_JP.findall(text)) / len(letters)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    parser.add_argument("--token", default="", help="bearer token if configured")
    args = parser.parse_args()

    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = "Bearer " + args.token

    jp_ok = cite_ok = honest_ok = asked = 0
    echo_mode = False
    for question, kind in QUESTIONS:
        body = json.dumps({"message": question}).encode("utf-8")
        request = urllib.request.Request(
            args.base + "/v1/chat", data=body, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - a dead server is the finding
            print(f"NG  {question[:24]}  ({type(exc).__name__})")
            continue
        asked += 1
        answer = payload.get("answer") or ""
        if "echo" in (payload.get("model") or "").lower() or answer.startswith("[echo]"):
            echo_mode = True
        share = japanese_share(answer)
        cited = bool(re.search(r"\[S\d+\]", answer)) or bool(payload.get("citations"))
        if share >= 0.3:
            jp_ok += 1
        if cited:
            cite_ok += 1
        honesty = "-"
        if kind == "absent":
            invented = bool(_NUMBER.search(answer)) and "円" in answer
            honesty = "NG" if invented else "OK"
            if honesty == "OK":
                honest_ok += 1
        print(
            f"{'OK' if share >= 0.3 else 'NG'}  jp={share:4.0%} cite={'Y' if cited else 'N'} "
            f"honest={honesty}  {question[:28]}"
        )

    print("-" * 56)
    if echo_mode:
        print("echo backend detected: language numbers describe echo, not the model")
    print(
        f"日本語率 {jp_ok}/{asked} / 引用付き {cite_ok}/{asked} / "
        f"根拠なし質問の誠実さ {honest_ok}/2"
    )
    print("数字は docs/OUTCOMES.md の「実機モデル測定」節へ手で記録すること。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
