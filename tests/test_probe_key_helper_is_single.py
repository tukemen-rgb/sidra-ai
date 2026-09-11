"""One name, one function (C-1656).

C-1651 put the key/code pairing in one place because a rule that every
probe retypes is a rule that comes back wrong. C-1652, running in
parallel, added a second ``probeKey`` in ``probekit`` - three arguments
instead of one, dispatching as well as building - behind the *same*
injection token. Nothing failed: each probe was internally consistent.
But the one name meant two functions depending on which builder ran, and
swapping a builder would have produced a probe that dispatched nothing at
all, which is quieter than a crash and worse than one.

So: the branch is defined in exactly one module, and no assembled probe
may end up with two definitions of it.
"""

from __future__ import annotations

import pathlib
import re

from sidra_ai.creation import probekit


def _creation_dir() -> pathlib.Path:
    return pathlib.Path(probekit.__file__).parent


def test_only_probekeys_defines_the_pairing() -> None:
    """Any other module defining `function probeKey` is a second answer to
    a name that already has one."""

    offenders = []
    for path in sorted(_creation_dir().glob("*.py")):
        if path.name == "probekeys.py":
            continue
        if re.search(r"function probeKey\s*\(", path.read_text(encoding="utf-8")):
            offenders.append(path.name)

    assert offenders == [], offenders


def test_probekit_does_not_define_it() -> None:
    for name in ("PROBE_SEND", "PROBE_SHAKE", "PROBE_EARS", "PROBE_EYES"):
        assert hasattr(probekit, name), name
    assert not hasattr(probekit, "PROBE_KEYS"), "the duplicate must be gone"
    assert probekit.PROBE_SEND.count("function probeKey") == 1
    assert probekit.PROBE_SEND.count("function probeSend") == 1


def test_no_assembled_probe_carries_two_definitions() -> None:
    """The real hazard is at assembly: a probe that embeds both helpers."""

    import re as _re
    import subprocess  # noqa: F401  (kept: probes are built, not run, here)

    from sidra_ai.creation.duel import ladder_probe as duel_ladder
    from sidra_ai.creation.marble import ladder_probe as marble_ladder
    from sidra_ai.creation.platformer import ladder_probe as plat_ladder
    from sidra_ai.creation.shooter import ladder_probe as shooter_ladder
    from sidra_ai.creation.adventure import knock_probe, scene_order_probe

    for name, builder in (
        ("platformer", plat_ladder), ("marble", marble_ladder),
        ("shooter", shooter_ladder), ("duel", duel_ladder),
        ("adventure/knock", knock_probe), ("adventure/scene", scene_order_probe),
    ):
        built = builder("/* page */")
        assert built.count("function probeKey") <= 1, name
        assert "PROBE_SEND_PLACEHOLDER" not in built, f"{name}: slot left unfilled"
        assert "PROBE_KEYS_PLACEHOLDER" not in built, f"{name}: slot left unfilled"


def test_the_dispatcher_stops_when_a_listener_says_stop() -> None:
    """The templates' own listeners call ``stopImmediatePropagation``; a
    probe that kept dispatching past it would be feeding the page events a
    browser would have withheld, and the measurement would be of something
    no player could cause."""

    import json
    import shutil
    import subprocess

    import pytest

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to run the snippet")

    script = (
        probekit.PROBE_SEND
        + """
const seen = [];
const handlers = { keydown: [
  function(e){ seen.push('first'); e.stopImmediatePropagation() },
  function(e){ seen.push('second') } ] };
probeSend('keydown', ' ', handlers);
console.log(JSON.stringify({ seen: seen }));
"""
    )
    out = subprocess.run(
        ["node", "-"], input=script, capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr[:400]
    seen = json.loads(out.stdout.strip().splitlines()[-1])["seen"]

    assert seen == ["first"], seen
