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
  1  could not reach the API, or the API returned an error
  2  refused to run - unsafe configuration or bad usage
  3  the security gate refused to answer

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
        "--top-k", type=int, default=5, help="how many chunks to retrieve (default 5)"
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


def _print_citations(payload: dict[str, Any], clean: _Stripped) -> None:
    citations = payload.get("citations") or []
    if not citations:
        print("\n引用なし。索引に根拠が無いか、取り込みがまだ走っていない。")
        return

    print("\n引用:")
    for citation in citations:
        label = clean(citation.get("label", "?"))
        reference = clean(citation.get("citation", ""))
        marks = []
        if citation.get("redacted"):
            marks.append("一部秘匿")
        trust = clean(citation.get("trust_level", ""))
        if trust and trust != "internal_repo":
            marks.append(trust)
        suffix = f"  ({', '.join(marks)})" if marks else ""
        print(f"  [{label}] {reference}{suffix}")


def render(payload: dict[str, Any]) -> int:
    """Print one chat response. Returns the process exit code."""

    clean = _Stripped()

    if payload.get("refused"):
        print("回答を拒否した。")
        reason = clean(payload.get("reason", ""))
        if reason:
            print(f"理由: {reason}")
        _print_citations(payload, clean)
        _report_stripped(clean)
        return 3

    answer = clean(payload.get("answer", "")).strip()
    print(answer if answer else "(空の回答)")
    _print_citations(payload, clean)

    model = payload.get("model") or {}
    if model.get("backend"):
        cost = model.get("external_api_cost_usd")
        cost_note = f", 外部 API 費用 ${cost}" if cost is not None else ""
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

    try:
        settings = get_settings()
        url = base_url(settings, args.url)
        headers = authorization_header(url, settings)
    except UnsafeConfigurationError as exc:
        print(f"refusing to ask: {exc}", file=sys.stderr)
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
            print(
                f"{url} に接続できない。`sidra-api` を起動しているか、"
                "SIDRA_HOST / SIDRA_PORT が合っているか確認する。",
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
            print(f"要求に失敗した: {type(exc).__name__}", file=sys.stderr)
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
    if response.status_code == 429:
        print("レート制限に当たった。少し待って再試行する。", file=sys.stderr)
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
        # json.dumps escapes control characters, so the raw view is safe to
        # print without stripping anything from it.
        print(json.dumps(payload_out, ensure_ascii=False, indent=2))
        return 3 if payload_out.get("refused") else 0

    return render(payload_out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
