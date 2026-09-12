"""Does an out-of-range SIDRA_PORT say what the valid range is?

C-1740. ``Settings.validate()`` names the constraint for every bounded or
enumerated setting it checks - the allowed model backends, the minimum ingest
interval, the required token length, the keep-alive shapes - except ``port``,
which raised a bare ``"port out of range"``. Port is the setting an operator is
most likely to change (to run on a custom port), so the one message that names
no range guards the value most people touch. A user who sets ``SIDRA_PORT=0`` or
``SIDRA_PORT=70000`` is told only that it is wrong, not that the range is 1-65535
nor what they gave - the same misdirection C-1661 fixed for ``--top-k``.

``validate()`` now names the offending value and the 1-65535 range, matching its
own siblings. The checks drive the real ``Settings.validate()``: out-of-range
values (0, 70000, 65536) raise with the range named and the value echoed, and the
boundaries (1, 65535) and a typical custom port (8080) still validate.
"""

from __future__ import annotations

from dataclasses import dataclass


def _port_error(port: int) -> str | None:
    """Return the validation error message for ``port``, or ``None`` if it passes."""

    from sidra_ai.config.settings import Settings, UnsafeConfigurationError

    try:
        Settings(port=port).validate()
    except UnsafeConfigurationError as exc:
        return str(exc)
    return None


@dataclass(frozen=True)
class ConfigPortRangeResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_config_port_out_of_range_is_named() -> ConfigPortRangeResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    low = _port_error(0)
    high = _port_error(70000)
    just_over = _port_error(65536)

    # --- (A) port 0 is refused and the valid range is named (1 and 65535) ---
    add(low is not None and "1" in low and "65535" in low,
        f"A: port 0 error did not name the 1-65535 range: {low!r}")

    # --- (B) a too-large port is refused and the offending value is echoed ---
    add(high is not None and "70000" in high,
        f"B: port 70000 error did not echo the offending value: {high!r}")

    # --- (C) just above the ceiling is refused with the range named ---
    add(just_over is not None and "65535" in just_over,
        f"C: port 65536 was not refused with the range named: {just_over!r}")

    # --- (D) the low boundary (1) validates ---
    add(_port_error(1) is None, f"D: port 1 was wrongly refused: {_port_error(1)!r}")

    # --- (E) the high boundary (65535) validates ---
    add(_port_error(65535) is None,
        f"E: port 65535 was wrongly refused: {_port_error(65535)!r}")

    # --- (F) a typical custom port validates (no over-broadening) ---
    add(_port_error(8080) is None,
        f"F: a typical custom port 8080 was refused: {_port_error(8080)!r}")

    total = 6
    return ConfigPortRangeResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=total,
        failures=tuple(failures),
    )


__all__ = ["ConfigPortRangeResult", "evaluate_config_port_out_of_range_is_named"]
