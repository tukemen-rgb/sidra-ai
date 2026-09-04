"""Does the CLI report a config-safety error in Japanese, not English?

C-1243: the CLI mapped every HTTP status, the network catch-all and the gate
refusal to Japanese (C-1223/C-1233/C-1238), but a config-safety failure still
printed 「refusing to ask: <English>」 - an English prefix. A Japanese user who
misconfigured SIDRA_HOST got English, against SYSTEM_PROMPT rule 6. The prefix
is now Japanese with a next step; the exception detail (which names the config
variable) stays in parentheses, the way the HTTP branches keep their code.

The checks drive main() with get_settings patched to raise the real error and
confirm the guidance is Japanese, the English prefix is gone, the detail
survives, and the exit code is unchanged. An empty question still returns 2.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from dataclasses import dataclass

_ENGLISH_PREFIX = "refusing to ask"
_DETAIL = "refusing to bind non-loopback host 'example.com': set SIDRA_ALLOW_PUBLIC_BIND=true"


@dataclass(frozen=True)
class CliConfigErrorResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _run_config_error() -> tuple[int, str]:
    from sidra_ai.api import ask_cli
    from sidra_ai.config import UnsafeConfigurationError

    original = ask_cli.get_settings

    def _raise() -> object:
        raise UnsafeConfigurationError(_DETAIL)

    ask_cli.get_settings = _raise  # type: ignore[assignment]
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            code = ask_cli.main(["質問"])
    finally:
        ask_cli.get_settings = original  # type: ignore[assignment]
    return code, err.getvalue()


def evaluate_cli_config_error_japanese() -> CliConfigErrorResult:
    checks = 0
    failures: list[str] = []

    code, out = _run_config_error()

    # 1: exit code stays 2 (a usage/config refusal).
    if code == 2:
        checks += 1
    else:
        failures.append(f"exit code was {code}, expected 2")

    # 2: the English prefix is gone.
    if _ENGLISH_PREFIX not in out:
        checks += 1
    else:
        failures.append("the English 'refusing to ask' prefix is still shown")

    # 3: the message carries Japanese guidance (a next step, not just a label).
    if "設定" in out and ("見直" in out or "確認" in out):
        checks += 1
    else:
        failures.append("no Japanese guidance about reviewing the configuration")

    # 4: the exception detail survives (it names the config variable to fix).
    if "SIDRA_ALLOW_PUBLIC_BIND" in out:
        checks += 1
    else:
        failures.append("the config detail (variable to fix) was dropped")

    # 5: an empty question still returns 2 in Japanese (unaffected).
    from sidra_ai.api import ask_cli

    empty = io.StringIO()
    with redirect_stderr(empty):
        empty_code = ask_cli.main([" "])
    if empty_code == 2 and "質問が空" in empty.getvalue():
        checks += 1
    else:
        failures.append("empty-question handling regressed")

    return CliConfigErrorResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=5,
        failures=tuple(failures),
    )
