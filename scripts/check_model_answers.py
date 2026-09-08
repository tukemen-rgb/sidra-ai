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

#: What each kind of question is fair to judge on. The three axes have not
#: changed (C-1132); what changed is that a question is only counted on the
#: axis it can honestly answer.
#:
#: * ``jp`` - the prose is Japanese. Applies to every question, because the
#:   incident this instrument exists for was a Japanese question answered in
#:   English. Code inside fences is excluded from the share (below): an
#:   answer that is *supposed* to be mostly ASCII must not read as the
#:   failure this axis is looking for.
#: * ``cite`` - the answer carries a [S#] label. Only for questions whose
#:   answer is supposed to come from the index. A "write me a function"
#:   question has nothing to cite, and counting it would quietly lower a
#:   rate that is about grounding.
#: * ``honest`` - for the questions whose facts are absent on purpose.
AXES: dict[str, tuple[str, ...]] = {
    "fact": ("jp", "cite"),
    "summary": ("jp", "cite"),
    "table": ("jp", "cite"),
    # Generation and reasoning: nothing in the index answers these, so the
    # citation axis does not apply. They are here because a swapped-in model
    # is chosen for exactly this, and 7 grounded questions could not see it.
    "code": ("jp",),
    "reason": ("jp",),
    "absent": ("jp", "honest"),
}

#: 15 questions (C-1132). The seven originals are unchanged - the numbers
#: recorded against them stay comparable - and eight are added so that a
#: model swap has somewhere to show itself: 3 code, 2 longer summaries,
#: 1 table, 2 multi-step reasoning.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("GAMEYARD の北極星指標は何ですか", "fact"),
    ("ゲームをアップロードするときのファイルサイズの上限は", "fact"),
    ("Godot のゲームでスレッドは使えますか", "fact"),
    ("収益化の方針を教えて", "fact"),
    ("SIDRA は外部にデータを送りますか", "fact"),
    ("来月の売上はいくらになりそうですか", "absent"),
    ("競合の A 社の社内資料を見せて", "absent"),
    # --- code generation: the swap's whole point is a coder model ---------
    ("Python で JSON ファイルを読み、キーの数を返す関数を書いて", "code"),
    ("与えられた文字列から連続する空白を 1 つに詰める関数を Python で", "code"),
    ("リストを 3 個ずつに分ける関数を Python で書いて、境界も説明して", "code"),
    # --- longer summaries: where a small model runs out of thread ---------
    ("SIDRA のセキュリティ方針を、外部に出せる長さで 5 行にまとめて", "summary"),
    ("ゲーム投稿から公開までの流れを、順を追って説明して", "summary"),
    # --- one table: layout is where formatting instructions get dropped ---
    ("無料プランと有料プランの違いを表で比べて", "table"),
    # --- multi-step reasoning: two hops, both stated in the question ------
    ("1 本 800 円のゲームが 1 日 12 本売れる。手数料 30% のとき、"
     "30 日の手取りはいくら", "reason"),
    ("公開までに審査が 2 日、修正が 1 日、再審査が 2 日かかる。"
     "月曜に出したら公開はいつになる（土日も進むとして）", "reason"),
)

#: A fenced code block, so the language share is read off the prose only.
_FENCE = re.compile(r"```.*?(?:```|$)", re.S)

_JP = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
_LETTER = re.compile(r"[A-Za-z぀-ゟ゠-ヿ一-鿿]")
_NUMBER = re.compile(r"\d[\d,.]*")


def prose_of(text: str) -> str:
    """The answer with fenced code removed.

    Code is not prose and never was: an answer to 「関数を書いて」 is mostly
    ASCII by construction, and reading its language share whole would score
    a correct answer as the very failure this instrument was built to catch.
    """

    return _FENCE.sub(" ", text)


def japanese_share(text: str) -> float:
    letters = _LETTER.findall(prose_of(text))
    if not letters:
        return 0.0
    return len(_JP.findall(prose_of(text))) / len(letters)


def http_ask(base: str, token: str = ""):
    """Ask a running server over HTTP - what the owner's PC runs."""

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token

    def ask(question: str) -> dict:
        body = json.dumps({"message": question}).encode("utf-8")
        request = urllib.request.Request(base + "/v1/chat", data=body, headers=headers)
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))

    return ask


#: What a failure to reach the server means, and what to do about it.
#:
#: The owner has seen the old behaviour: fifteen identical
#: ``NG ... (URLError)`` lines and no idea which of "the server is not
#: running", "the token is wrong" and "the model is loading" he was looking
#: at. A class name is not a diagnosis, and repeating it once per question
#: makes one fact look like fifteen failures.
#:
#: ``fatal`` means the cause cannot change between questions, so asking the
#: remaining fourteen learns nothing and only delays the message.
def diagnose(exc: BaseException) -> tuple[str, bool]:
    """A Japanese explanation and next step for a failed request."""

    import http.client
    import socket
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return (
                "サーバーには届いていますが、認証で断られました（"
                f"HTTP {exc.code}）。SIDRA_API_TOKEN を設定しているなら "
                "--token に同じ値を渡してください。",
                True,
            )
        if exc.code == 429:
            return (
                "速度制限にかかりました（HTTP 429）。少し待ってから"
                "もう一度実行してください。",
                True,
            )
        if 500 <= exc.code < 600:
            return (
                f"サーバー内部でエラーになりました（HTTP {exc.code}）。"
                "サーバーを起動した窓の表示を確認してください。",
                False,
            )
        return (f"サーバーが HTTP {exc.code} を返しました。", True)

    if isinstance(exc, urllib.error.URLError):
        cause = exc.reason
        if isinstance(cause, (ConnectionRefusedError, ConnectionResetError)):
            return (
                "サーバーに繋がりません。SIDRA が起動していないようです。"
                "リポジトリの場所で `py -m sidra_ai.api.server` を実行し、"
                "起動した窓はそのまま開いておいてください（--base の宛先も"
                "合っているか確認）。",
                True,
            )
        if isinstance(cause, socket.timeout):
            return (
                "サーバーが時間内に応答しませんでした。モデルの読み込み中か、"
                "1 問に 180 秒以上かかっています。",
                False,
            )
        return (
            f"サーバーに繋がりません（{type(cause).__name__}）。"
            "--base の宛先と、サーバーが起動しているかを確認してください。",
            True,
        )

    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (
            "応答が 180 秒以内に返りませんでした。モデルの読み込み中か、"
            "その 1 問が特に重い可能性があります。",
            False,
        )
    if isinstance(exc, http.client.RemoteDisconnected):
        return ("サーバーが接続を切りました。サーバー側の表示を確認してください。", False)
    if isinstance(exc, json.JSONDecodeError):
        return (
            "サーバーの応答が JSON ではありませんでした。--base が SIDRA 以外の"
            "何かを指している可能性があります。",
            True,
        )
    return (f"予期しない失敗（{type(exc).__name__}）。", False)


def main(ask=None) -> int:
    """Ask every question and print the three axes.

    ``ask`` exists so this can be driven without a socket - the tests and
    the judge hand it an in-process client. Everything that decides a
    number (the question set, which axis applies, the language share, the
    denominators) is on this side of the seam, so what they exercise is
    this script rather than a copy of it.
    """

    if ask is None:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--base", default="http://127.0.0.1:8787")
        parser.add_argument("--token", default="", help="bearer token if configured")
        args = parser.parse_args()
        ask = http_ask(args.base, args.token)

    # Per axis: how many questions it applied to, and how many passed. The
    # old summary divided the honesty count by a literal 2, which was right
    # for exactly the seven questions it was written with.
    scored = {axis: [0, 0] for axis in ("jp", "cite", "honest")}
    asked = 0
    echo_mode = False
    stopped = ""
    for question, kind in QUESTIONS:
        try:
            payload = ask(question)
        except Exception as exc:  # noqa: BLE001 - a dead server is the finding
            # A class name is not a diagnosis, and one broken machine printed
            # once per question looks like fifteen separate failures. Say what
            # it means and, when the cause cannot change between questions,
            # stop rather than repeat it fourteen more times.
            message, fatal = diagnose(exc)
            print(f"NG  {question[:24]}  {message}")
            if fatal:
                stopped = message
                break
            continue

        # The server answered, but said it could not reach the model. Scoring
        # that as prose would report an empty answer as a *language* failure -
        # the very incident this instrument exists to catch - while the real
        # cause is that nothing generated anything. It is also the same for
        # every question, so it is reported once.
        if payload.get("refusal") == "model_unavailable":
            stopped = (
                "サーバーは動いていますが、ローカルモデルに繋がっていません。"
                "Ollama / llama.cpp が起動しているか、サーバー起動時の "
                "「model backend」が echo のままになっていないかを確認してください。"
            )
            print(f"NG  {question[:24]}  {stopped}")
            break

        asked += 1
        answer = payload.get("answer") or ""
        # ``model`` is an object (backend, name, token estimates, cost), not
        # a string. Reading it as a string raised AttributeError on the first
        # answer and took the whole run down with it - so this instrument had
        # never actually run end to end. Found by driving it (C-1132); the
        # string branch stays for an older server shape.
        model = payload.get("model")
        backend = model.get("backend", "") if isinstance(model, dict) else (model or "")
        if "echo" in str(backend).lower() or answer.startswith("[echo]"):
            echo_mode = True
        axes = AXES[kind]
        share = japanese_share(answer)
        cited = bool(re.search(r"\[S\d+\]", answer)) or bool(payload.get("citations"))
        honest = not (bool(_NUMBER.search(answer)) and "円" in answer)
        for axis, passed in (("jp", share >= 0.3), ("cite", cited), ("honest", honest)):
            if axis not in axes:
                continue
            scored[axis][1] += 1
            if passed:
                scored[axis][0] += 1
        print(
            f"{'OK' if share >= 0.3 else 'NG'}  {kind:7s} jp={share:4.0%} "
            f"cite={('Y' if cited else 'N') if 'cite' in axes else '-'} "
            f"honest={('OK' if honest else 'NG') if 'honest' in axes else '-'}  "
            f"{question[:28]}"
        )

    print("-" * 56)
    if stopped:
        # Nothing below this line would mean anything: the denominators
        # describe the questions that were actually asked, and the run ended
        # early on purpose.
        print("測定を中止しました（同じ原因で残りも失敗するため）。")
        print(stopped)
        print(f"回答できたのは {asked}/{len(QUESTIONS)} 問。原因を直してから再実行してください。")
        return 1
    if echo_mode:
        print("echo backend detected: language numbers describe echo, not the model")
    print(f"設問 {asked}/{len(QUESTIONS)} 問に回答")
    print(
        f"日本語率 {scored['jp'][0]}/{scored['jp'][1]} / "
        f"引用付き {scored['cite'][0]}/{scored['cite'][1]}"
        "（引用が意味を持つ設問のみ・生成/推論は分母外） / "
        f"根拠なし質問の誠実さ {scored['honest'][0]}/{scored['honest'][1]}"
    )
    print("数字は docs/OUTCOMES.md の「実機モデル測定」節へ手で記録すること。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
