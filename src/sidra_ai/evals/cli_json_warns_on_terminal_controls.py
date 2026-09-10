"""Does ``sidra-ask --json`` warn when its raw output carries terminal controls?

C-1627. ``ask_cli`` declares in its own docstring that it is responsible for
「表示するものは実行しない」: the rendered path strips the C0/C1 controls, bidi
overrides and zero-width characters that a repository DATA excerpt can use to
rewrite a terminal, and it reports the removal on stderr 「rather than done
silently」. The ``--json`` path skipped all of it on the belief - stated in a
code comment and in the closed history item at commit 8c7eacb - that
「json.dumps escapes control characters, so the raw view is safe」.

That belief is only true for U+0000–U+001F. ``json.dumps(ensure_ascii=False)``
escapes ESC to ``\\u001b`` but emits U+0085/U+009B (C1, and U+009B is the CSI
that opens an ANSI sequence), the bidi overrides U+202E/U+2066, the zero-width
U+200B/U+FEFF and U+007F (DEL) **raw**. A human eyeballing ``--json`` output in
a terminal therefore gets exactly the sequences the rendered path guards
against, with no warning.

``--json`` must stay byte-faithful for a machine consumer, so nothing is
removed from stdout. Instead the terminal-hostile codepoints that survive into
the raw view are counted, and their presence is reported on stderr - the same
「reported rather than done silently」 contract the rendered path keeps.

The checks drive the real ``main`` down the ``--json`` branch with a stub
transport and read stdout (the JSON, which must keep the raw bytes) and stderr
(the warning).
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

# The codepoints render() strips that json.dumps does NOT escape, one per
# category. ESC is the discriminator: json escapes it, so it must never warn.
_NEL = chr(0x85)  # C1 control
_CSI = chr(0x9B)  # C1 control that opens an ANSI escape sequence
_RLO = chr(0x202E)  # bidi override
_LRI = chr(0x2066)  # bidi isolate
_ZWSP = chr(0x200B)  # zero-width
_BOM = chr(0xFEFF)  # zero-width / BOM
_DEL = chr(0x7F)  # DEL
_ESC = chr(0x1B)  # sub-0x20: json.dumps escapes this to a \uXXXX literal


def _run_json(payload: dict) -> tuple[int, str, str]:
    """Drive ``main --json`` with a stub transport; return (code, out, err)."""

    from sidra_ai.api import ask_cli
    from sidra_ai.config.settings import Settings

    class _Resp:
        status_code = 200

        def json(self):
            return payload

    class _Client:
        def __init__(self):
            self.headers = {}

        def post(self, *a, **k):
            return _Resp()

        def close(self):
            pass

    out, err = io.StringIO(), io.StringIO()
    original = ask_cli.get_settings
    ask_cli.get_settings = lambda: Settings(data_dir="/tmp/sidra-eval-cli-json")
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ask_cli.main(["質問", "--json"], client=_Client())
    finally:
        ask_cli.get_settings = original
    return code, out.getvalue(), err.getvalue()


def _answer(text: str) -> dict:
    return {
        "refused": False,
        "answer": text,
        "citations": [],
        "security": {"decision": "allow"},
        "model": {"backend": "echo"},
    }


@dataclass(frozen=True)
class CliJsonControlsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_cli_json_warns_on_terminal_controls() -> CliJsonControlsResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    def warned(err: str) -> bool:
        return "注意" in err and "端末制御文字" in err

    # (A) A clean answer carries no hostile codepoint: no warning at all.
    _, _, err = _run_json(_answer("索引済み DATA から回答します。"))
    add(not warned(err), f"clean payload warned: {err!r}")

    # (B) ESC only: json.dumps escapes it, so the raw view is genuinely safe and
    # must not warn - and stdout must NOT contain the raw ESC (proof the check
    # keys on the serialized output, not the payload).
    code_esc, out_esc, err_esc = _run_json(_answer("A" + _ESC + "B"))
    add(not warned(err_esc), f"ESC-only payload warned: {err_esc!r}")
    add(_ESC not in out_esc, f"raw ESC leaked into --json stdout: {out_esc!r}")

    # (C) Each surviving-raw category warns on stderr.
    for name, ch in (
        ("NEL", _NEL), ("CSI", _CSI), ("RLO", _RLO), ("LRI", _LRI),
        ("ZWSP", _ZWSP), ("BOM", _BOM), ("DEL", _DEL),
    ):
        _, _, err = _run_json(_answer("A" + ch + "B"))
        add(warned(err), f"{name} did not warn: {err!r}")

    # (D) stdout stays byte-faithful: the raw char is still there for a machine.
    for name, ch in (("CSI", _CSI), ("RLO", _RLO), ("DEL", _DEL)):
        _, out, _ = _run_json(_answer("A" + ch + "B"))
        add(ch in out, f"{name} raw byte dropped from --json stdout: {out!r}")

    # (E) The warning names how many hostile chars are in the raw view.
    _, _, err3 = _run_json(_answer("A" + _NEL + _RLO + _ZWSP + "B"))
    add(warned(err3) and "3" in err3, f"count not reported as 3: {err3!r}")

    # (F) The warning is on stderr, never stdout: stdout parses as JSON.
    import json as _json

    _, out_f, _ = _run_json(_answer("A" + _CSI + "B"))
    try:
        _json.loads(out_f)
        stdout_clean = "注意" not in out_f
    except ValueError:
        stdout_clean = False
    add(stdout_clean, f"warning leaked into --json stdout: {out_f!r}")

    # (G) The exit code is unaffected: an answered response is still 0.
    code_g, _, _ = _run_json(_answer("A" + _CSI + "B"))
    add(code_g == 0, f"hostile-but-answered exit code was {code_g}, expected 0")

    total = 1 + 2 + 7 + 3 + 1 + 1 + 1
    return CliJsonControlsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["CliJsonControlsResult", "evaluate_cli_json_warns_on_terminal_controls"]
