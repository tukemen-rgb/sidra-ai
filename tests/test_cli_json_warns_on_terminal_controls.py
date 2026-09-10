"""C-1627: ``sidra-ask --json`` must report terminal-hostile codepoints that
``json.dumps`` leaves raw, on stderr, without altering the byte-faithful JSON on
stdout."""

from __future__ import annotations

from sidra_ai.evals.cli_json_warns_on_terminal_controls import (
    evaluate_cli_json_warns_on_terminal_controls,
)


def test_json_mode_warns_on_terminal_controls_passes_all_checks():
    result = evaluate_cli_json_warns_on_terminal_controls()
    assert result.passed, result.failures
    assert result.checks_passed == result.checks_total


def test_clean_json_output_is_not_warned():
    # A response with no hostile codepoint must not print the warning.
    from sidra_ai.evals.cli_json_warns_on_terminal_controls import _answer, _run_json

    _, _, err = _run_json(_answer("普通の日本語の回答です。"))
    assert "注意" not in err


def test_csi_is_reported_and_kept_faithful():
    # The C1 CSI (U+009B) opens an ANSI sequence: it is warned about, yet the
    # raw byte survives on stdout for a machine consumer.
    from sidra_ai.evals.cli_json_warns_on_terminal_controls import _answer, _run_json

    _, out, err = _run_json(_answer("A" + chr(0x9B) + "B"))
    assert "端末制御文字" in err
    assert chr(0x9B) in out
