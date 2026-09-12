"""``sidra-ask`` - ask SIDRA a question from the shell.

    sidra-ask "GAMEYARD の north star metric は何か"
    sidra-ask "..." --repository tukemen-rgb/Fg --top-k 3
    sidra-ask "..." --json

Until now the only way to ask was to hand-build JSON for ``POST /v1/chat``
and read the citations out of the response with ``jq``. A tool nobody reaches
for is a tool that does not exist, and the answer quality nobody sees is the
answer quality nobody fixes.

This does one thing: send the question, print the answer and where it came
from. It adds no capability the API does not already have.

Exit codes are distinct so a script can tell the cases apart:

  0  answered
  1  could not reach the API, or the API returned an error (including the
     model backend being unavailable, so no answer could be produced)
  2  refused to run - unsafe configuration or bad usage
  3  refused for safety - the security gate blocked the input or history, or
     the output guard withheld a generated answer

Two properties this file is responsible for
-------------------------------------------

**The token goes only where it was configured to go.** ``--url`` is useful
for reaching an instance on another port, and it is also a way to hand your
bearer token to any host that appears on a command line. The token is sent to
the configured host or to loopback, and any other target is refused outright
rather than quietly retried without auth - a silent downgrade surfaces as a
puzzling 401 instead of the actual problem.

**The answer is rendered, not executed.** Everything printed here derives
from repository content, which is DATA from outside. Control sequences in
that data are how a document rewrites a terminal: an escape sequence can
erase the citation that would have exposed it, and a bidi override can make
one repository's name read as another's. They are removed before printing,
and the removal is reported rather than done silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

from sidra_ai.api.schemas import TOP_K_MAX, TOP_K_MIN
from sidra_ai.config.settings import (
    LOCALHOST_ADDRESSES,
    Settings,
    UnsafeConfigurationError,
    get_settings,
)

#: Generation on a local 32B model is slow but not unbounded. Long enough that
#: a real answer is not cut off, short enough that a wedged server does not
#: hold the shell forever.
DEFAULT_TIMEOUT_SECONDS = 300.0

#: Characters removed before anything reaches a terminal.
#:
#: C0 minus tab/newline, DEL and C1 cover the escape sequences that move the
#: cursor, recolour, or clear the screen. The rest are invisible or
#: direction-changing characters that alter what a reader sees without
#: altering the text: zero-width joiners hide word boundaries, and the bidi
#: overrides make a citation display in an order it was not written in.
#: ``security/detectors.py`` flags these on the way in; this removes them on
#: the way out, because the gate can be widened and a terminal cannot.
_STRIPPED_CODEPOINTS = frozenset(
    [code for code in range(0x00, 0x20) if code not in (0x09, 0x0A)]
    + [0x7F]
    + list(range(0x80, 0xA0))
    + list(range(0x200B, 0x2010))
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A))
    + [0xFEFF]
)


class _Stripped:
    """Renders untrusted text for a terminal and remembers what it removed."""

    def __init__(self) -> None:
        self.removed = 0

    def __call__(self, value: object) -> str:
        text = str(value)
        kept = [character for character in text if ord(character) not in _STRIPPED_CODEPOINTS]
        self.removed += len(text) - len(kept)
        return "".join(kept)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sidra-ask",
        description="Ask SIDRA a question and print the answer with its citations",
    )
    parser.add_argument("question", help="the question, in quotes")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help=f"how many chunks to retrieve, {TOP_K_MIN}-{TOP_K_MAX} (default 5)",
    )
    parser.add_argument(
        "--repository",
        action="append",
        dest="repositories",
        default=None,
        metavar="OWNER/NAME",
        help="restrict retrieval to this repository (repeatable)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="API base URL (default: the configured SIDRA_HOST/SIDRA_PORT)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"seconds to wait for an answer (default {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the raw response instead of formatting it",
    )
    return parser


def base_url(settings: Settings, override: str | None) -> str:
    if override:
        return override.rstrip("/")
    host = f"[{settings.host}]" if ":" in settings.host else settings.host
    return f"http://{host}:{settings.port}"


def _host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def authorization_header(url: str, settings: Settings) -> dict[str, str]:
    """Attach the bearer token, or refuse to talk to this host at all.

    Sending the token only to the configured host is the whole point; the
    refusal is because dropping it instead would turn a misdirected request
    into an authentication error, which reads as "wrong token" and sends the
    reader looking in the wrong place.
    """

    token = settings.api_token
    if not token:
        return {}

    host = _host_of(url)
    if host and host != settings.host.lower() and host not in LOCALHOST_ADDRESSES:
        raise UnsafeConfigurationError(
            f"refusing to send the API token to {host!r}: it is neither the "
            f"configured host ({settings.host!r}) nor loopback"
        )
    return {"Authorization": f"Bearer {token}"}


#: A citation's trust level, shown to a Japanese reader the way the redaction
#: marks are (C-1469). ``internal_repo`` is the norm and stays suppressed; an
#: unknown future level falls back to its raw value rather than vanishing, so a
#: reader still sees *something* they can look up. ``--json`` keeps the raw enum.
_TRUST_LABELS = {
    "external": "外部",
    "unverified": "未検証",
    "operator": "運用者",
    "system": "システム",
}


def _print_citations(
    payload: dict[str, Any], clean: _Stripped, note_when_empty: bool = True
) -> None:
    citations = payload.get("citations") or []
    if not citations:
        # The "no evidence in the index" note explains an *answered* question
        # that found nothing. After a safety refusal there are also no citations,
        # but the reason is the gate, not the index - printing this note there
        # sends the reader to re-run ingestion for a problem ingestion cannot
        # fix (C-1254). The refusal path passes note_when_empty=False.
        if note_when_empty:
            print("\n引用なし。索引に根拠が無いか、取り込みがまだ走っていない。")
        return

    print("\n引用:")
    for citation in citations:
        label = clean(citation.get("label", "?"))
        reference = clean(citation.get("citation", ""))
        marks = []
        if citation.get("redacted"):
            marks.append("一部秘匿")
        # A whole-excerpt block at answer time (C-1236). Distinct from the
        # ingestion-time 「一部秘匿」 above: the service keeps them apart so a
        # reader can, and a citation whose excerpt was withheld reading exactly
        # like a plain one is the distinction going to waste.
        if citation.get("excerpt_withheld"):
            marks.append("抜粋を秘匿")
        trust = clean(citation.get("trust_level", ""))
        if trust and trust != "internal_repo":
            marks.append(_TRUST_LABELS.get(trust, trust))
        suffix = f"  ({', '.join(marks)})" if marks else ""
        print(f"  [{label}] {reference}{suffix}")
        # The excerpt the service selected so the reader can check the answer
        # against its source instead of taking repo/path/rank on faith - the web
        # UI's twin of this (C-1689), which left the CLI showing only the marks
        # (C-1691). Scrubbed through `clean` (so a control sequence in retrieved
        # content cannot reach the terminal, counted by _report_stripped) and
        # collapsed to one indented line beneath the citation. Shown only when
        # present, so a withheld excerpt still reads as 「抜粋を秘匿」 above.
        excerpt = " ".join(clean(citation.get("excerpt", "")).split())
        if excerpt:
            print(f"      {excerpt}")


def _refusal_exit_code(payload: dict[str, Any]) -> int:
    """The exit code for a refused response.

    Exit 3 is documented as "refused for safety"; exit 1 as "the API returned
    an error". Every refusal used to return 3, which put a **model backend
    unavailable** outage - an operational failure the docstring assigns to
    exit 1 - under the same code a script uses for a policy refusal (C-1456).

    A refusal is a *safety* refusal when the input gate blocked it
    (``security.decision`` is ``block``/``quarantine``, covering the message
    gate and the conversation-history gate) or when the output guard withheld a
    generated answer. The guard runs only after generation, so a ``model``
    metadata block means an answer was produced and then withheld (safety, 3);
    its absence with an ``allow`` decision means generation never happened
    (operational, 1). Keyed on the payload's shape, not on the reason text.
    """

    decision = (payload.get("security") or {}).get("decision")
    if decision in ("quarantine", "block"):
        return 3
    if payload.get("model"):
        return 3
    return 1


def render(payload: dict[str, Any], base_url: str = "") -> int:
    """Print one chat response. Returns the process exit code.

    ``base_url`` (the server this CLI is talking to) lets a creation name the
    ``/v1/artifacts/<name>`` route so the generated file is retrievable even when
    the client is not on the same machine as the server - the artifact_path alone
    is a server-side filesystem path (C-1705). Empty keeps the pre-existing
    path-only output for callers that do not pass it.
    """

    clean = _Stripped()

    if payload.get("refused"):
        print("回答を拒否した。")
        # The API reason is the gate's English audit text ("prompt-injection
        # patterns detected; …"); a terminal user reads Japanese and needs a
        # next step, not the audit trail (C-1238). The full English reason is
        # still in --json for anyone who needs it.
        #
        # Keyed on the payload's refusal code, the fixed identifier the service
        # sets on every refusal - the same codes the web UI uses (C-1157/C-1675).
        # security.decision alone could only tell a gate refusal from everything
        # else, so a stopped model, a blocked history and a withheld answer all
        # got "wait and try again" - advice that fixes none of them, since the
        # next step differs.
        messages = {
            "gate": "入力が安全性チェックにかかった。指示の上書きや秘密情報を含む"
                    "表現を避け、言い換えてもう一度試す。",
            "history": "回答を出せなかった。これまでの会話の中に安全性チェックに"
                       "かかる内容があった。会話をやり直すか、その部分を外して試す。",
            "model_unavailable": "回答を出せなかった。ローカルモデルに接続できていない。"
                                 "待っても直らない——モデル（Ollama / llama.cpp）が起動"
                                 "しているか、サーバ起動時の model backend が echo のまま"
                                 "でないか確認する。",
            "output_guard": "回答を出せなかった。答えの中に秘密や個人情報らしき箇所が"
                            "見つかったので全体を差し止めた。同じ質問なら同じ結果になる。",
            "empty": "質問が空である。調べたいことを入力する。",
        }
        message = messages.get(payload.get("refusal"))
        if message is None:
            # An unknown or absent code: fall back to what decision can tell.
            decision = (payload.get("security") or {}).get("decision")
            message = (
                "入力が安全性チェックにかかった。指示の上書きや秘密情報を含む"
                "表現を避け、言い換えてもう一度試す。"
                if decision in ("quarantine", "block")
                else "回答を出せなかった。少し時間をおいて、もう一度試す。"
            )
        print(message)
        # A refusal has no citations, and the "no evidence in the index" note
        # would misread as an ingestion problem (C-1254). Show citations only if
        # the gate somehow surfaced any; never the empty-index note.
        _print_citations(payload, clean, note_when_empty=False)
        _report_stripped(clean)
        return _refusal_exit_code(payload)

    answer = clean(payload.get("answer", "")).strip()
    print(answer if answer else "(空の回答)")

    # A creation response is not an index-grounded answer: it carries no
    # citations, and the empty-index note would misread as an ingestion problem
    # the same way it did after a refusal (C-1254). It also wrote a file the web
    # UI would list but the CLI never named, leaving the operator with a summary
    # and nowhere to look (C-1262). Show the path when one was written, and drop
    # the index note for creations. The key is the *outcome*, not the presence
    # of `creation`: every chat reply carries `creation.intent` metadata, so a
    # plain question has `creation` too - only a routed/declined creation has an
    # `outcome`, and only that should suppress the note. A genuine Q&A keeps it.
    outcome = (payload.get("creation") or {}).get("outcome") or {}
    artifact = outcome.get("artifact_path")
    if artifact:
        print(f"\n生成ファイル: {clean(str(artifact))}")
        # The path above is on the server's disk; a client reaching a non-local
        # server over --url cannot open it, whereas the web UI offers a download
        # by name (C-1705). Name the retrieval route too - but only for a flat
        # artifact, whose parent directory is `artifacts`, so the route is
        # unambiguously /v1/artifacts/<name>. A project file lives under
        # projects/<slug>/ and takes a different route, so it is left to its path
        # rather than risk printing a wrong URL.
        from pathlib import PurePosixPath

        art = PurePosixPath(str(artifact))
        if base_url and art.parent.name == "artifacts" and art.name:
            print(f"  取得: GET {clean(base_url)}/v1/artifacts/{clean(art.name)}")
        # A multi-file creation names only its preview in artifact_path: a 3D
        # model's .obj/.mtl and a deck's .pptx live in the details. The summary
        # tells the reader to open the .obj, so the CLI must give its path or it
        # repeats C-1262 (a summary and nowhere to look) for the other files.
        # Show every other *_path detail that was actually written.
        details = outcome.get("details") or {}
        for key in sorted(details):
            if not key.endswith("_path"):
                continue
            value = details[key]
            if value and str(value) != str(artifact):
                print(f"  {clean(str(value))}")
    _print_citations(payload, clean, note_when_empty=not outcome)

    model = payload.get("model") or {}
    if model.get("backend"):
        cost = model.get("external_api_cost_usd")
        # Only when a paid call actually cost something. v0.1 forbids external
        # APIs (usage.py raises on a paid call and totals() sums to 0.0, never
        # None), so `is not None` never suppressed the clause and every local
        # answer ended with "外部 API 費用 $0.0" - an external-API-cost line on a
        # product that never calls one, contradicting its local-first promise
        # on every answer. Show the clause only for a real cost; the backend
        # note (which reveals an echo silent-start, C-1664/C-1666) always stays.
        cost_note = f", 外部 API 費用 ${cost}" if cost else ""
        print(f"\n({clean(model['backend'])}{cost_note})")

    _report_stripped(clean)
    return 0


def _report_stripped(clean: _Stripped) -> None:
    if clean.removed:
        print(
            f"\n注意: 端末制御文字 {clean.removed} 個を取り除いて表示した。"
            " --json で元の値を確認できる。",
            file=sys.stderr,
        )


def ask(client: httpx.Client, url: str, payload: dict[str, Any]) -> httpx.Response:
    return client.post(f"{url}/v1/chat", json=payload)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.question.strip():
        print("質問が空である", file=sys.stderr)
        return 2

    # --top-k's range is a fixed client-visible contract (schemas.TOP_K_MIN/MAX).
    # Catch it here, before a request is built, so an out-of-range value names
    # the knob the reader actually used instead of being sent and rendered as a
    # 422 "your input is too long; shorten it" - which sends them to edit the
    # question, the one thing that cannot fix a bad --top-k (C-1661). Bad usage
    # is exit 2, the same as an empty question, not the transport's exit 1.
    if not TOP_K_MIN <= args.top_k <= TOP_K_MAX:
        print(
            f"--top-k は {TOP_K_MIN}〜{TOP_K_MAX} の範囲で指定する（指定値: {args.top_k}）。",
            file=sys.stderr,
        )
        return 2

    # A non-positive timeout is bad usage, caught here before a client is built.
    # httpx accepts a negative value at construction but raises
    # `ValueError: Timeout value out of range` on the request - which the
    # try/except below does not catch, so it crashed with a raw traceback; a
    # zero timeout made every request time out immediately and misreported
    # "cannot connect". Name the knob and exit 2, like --top-k (C-1673).
    if args.timeout <= 0:
        print(
            f"--timeout は正の秒数で指定する（指定値: {args.timeout:g}）。",
            file=sys.stderr,
        )
        return 2

    try:
        settings = get_settings()
        url = base_url(settings, args.url)
        headers = authorization_header(url, settings)
    except UnsafeConfigurationError as exc:
        # The CLI's other failures speak Japanese (C-1223/C-1233/C-1238); this
        # config-safety refusal was the last English prefix (C-1243). The
        # exception names the setting to fix, so it stays in parentheses the way
        # the HTTP branches keep their code - a Japanese next step, English
        # detail.
        print(
            f"設定が安全でないため実行を中止した。設定を見直して再実行する。（{exc}）",
            file=sys.stderr,
        )
        return 2

    # --repository is a client-visible contract (the allowlist), so a name that
    # is misspelt or not allowlisted is caught here, before a request is built.
    # Sent, it comes back as a 403 the CLI renders as "check your token" - which
    # sends the reader to fix authentication when the repository name is the one
    # thing that fixes it. Name the knob and the repositories that are allowed;
    # bad usage is exit 2, like an empty question or an out-of-range --top-k
    # (C-1669). This mirrors the server's own allowlist check.
    if args.repositories:
        unknown = [
            repository
            for repository in args.repositories
            if not settings.is_repository_allowed(repository)
        ]
        if unknown:
            print(
                f"--repository に許可されていないリポジトリを指定した: "
                f"{'、'.join(unknown)}。"
                f"（許可済み: {'、'.join(settings.allowed_repositories)}）",
                file=sys.stderr,
            )
            return 2

    payload: dict[str, Any] = {"message": args.question, "top_k": args.top_k}
    if args.repositories:
        payload["repositories"] = args.repositories

    owned = client is None
    http = client or httpx.Client(timeout=args.timeout, headers=headers)
    try:
        if client is not None and headers:
            http.headers.update(headers)
        try:
            response = ask(http, url, payload)
        except httpx.ConnectError:
            # Name the knob the reader actually used. With --url the target came
            # from that flag, so pointing them at SIDRA_HOST / SIDRA_PORT - which
            # they did not set - sends them to the wrong place (C-1278). The
            # generic HTTPError branch below already adapts this way.
            knob = "--url の指定" if args.url else "SIDRA_HOST / SIDRA_PORT"
            print(
                f"{url} に接続できない。`sidra-api` を起動しているか、"
                f"{knob}が合っているか確認する。",
                file=sys.stderr,
            )
            return 1
        except httpx.TimeoutException:
            print(
                f"{args.timeout:g} 秒以内に応答が無かった。"
                " ローカルモデルの生成が遅い場合は --timeout を伸ばす。",
                file=sys.stderr,
            )
            return 1
        except httpx.HTTPError as exc:
            # Every other transport failure: a peer that closed mid-answer
            # (RemoteProtocolError), a bad --url scheme (UnsupportedProtocol),
            # a lower-level protocol error. A bare English class name told a
            # terminal user nothing to do (C-1233), so the guidance is
            # Japanese and the class stays in parentheses for debugging - the
            # same shape the HTTP-status branches use with their code.
            print(
                "通信に失敗した。接続が途中で切れていないか、"
                "--url の指定が正しいか確認する。"
                f"（{type(exc).__name__}）",
                file=sys.stderr,
            )
            return 1
    finally:
        if owned:
            http.close()

    if response.status_code == 401:
        print(
            "認証に失敗した。SIDRA_API_TOKEN が API 側と一致しているか確認する。",
            file=sys.stderr,
        )
        return 1
    # The web page maps the reachable status classes to guidance (C-1211);
    # the CLI only had 401 and 429, so a too-long question - the most common
    # 422 a terminal user hits - printed a bare 「HTTP 422」 with no next step
    # (C-1223). The response body stays unread either way: a detail the API
    # kept private stays private, but the class of failure is not a secret,
    # and the code is still printed for debugging.
    if response.status_code == 403:
        print(
            "アクセスが拒否された。トークンと権限を確認する。（HTTP 403）",
            file=sys.stderr,
        )
        return 1
    if response.status_code in (413, 422):
        print(
            "入力が長すぎるか形式が不正。短くして再送する。"
            f"（HTTP {response.status_code}）",
            file=sys.stderr,
        )
        return 1
    if response.status_code == 429:
        print("レート制限に当たった。少し待って再試行する。（HTTP 429）", file=sys.stderr)
        return 1
    if response.status_code >= 500:
        print(
            "サーバ側で問題が起きた。時間をおいて再試行する。"
            f"（HTTP {response.status_code}）",
            file=sys.stderr,
        )
        return 1
    if response.status_code >= 400:
        print(f"API がエラーを返した: HTTP {response.status_code}", file=sys.stderr)
        return 1

    try:
        payload_out = response.json()
    except ValueError:
        print("API の応答が JSON ではない", file=sys.stderr)
        return 1

    if args.as_json:
        # json.dumps escapes only the JSON-mandated controls (U+0000-U+001F);
        # the C1 controls, bidi overrides and zero-width characters render()
        # strips survive into the raw view unescaped. --json stays byte-faithful
        # for a machine consumer, so they are not removed here - but a human
        # eyeballing the raw output is warned on stderr, the same "reported
        # rather than done silently" promise render() keeps (C-1627).
        raw = json.dumps(payload_out, ensure_ascii=False, indent=2)
        print(raw)
        hostile = sum(1 for character in raw if ord(character) in _STRIPPED_CODEPOINTS)
        if hostile:
            print(
                f"\n注意: 生の応答に端末制御文字 {hostile} 個が含まれる"
                "（--json は機械向けにそのまま出力するので取り除いていない）。",
                file=sys.stderr,
            )
        return _refusal_exit_code(payload_out) if payload_out.get("refused") else 0

    return render(payload_out, base_url=url)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
