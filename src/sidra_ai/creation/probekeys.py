"""One place that knows a keyboard event has two halves.

C-1623 found a probe pressing a key no page was listening for: it put the
key into ``code`` as well, so the space bar arrived as ``code: ' '`` - a
code no browser produces - and every template gating on
``e.code === 'Space'`` sat untouched through five thousand frames of
"mashing". C-1626 found the same mistake in eight more places, and in one
of them it had hardened into a written conclusion.

``test_probe_key_events`` scans the sources for that mistake, and it works:
it caught the same slip twice more in a single session (C-1645's scene
probe, C-1650's ear/eye probe). But a scan *detects* a recurrence; it does
not *prevent* one. The cause is that every probe hand-copies the same
three lines, and the space bar is the one key where copying them wrong
still looks like it works - adventure listens on ``e.key``, and racing's
own probe only ever pressed ``r``.

So the branch lives here once, and a probe embeds it instead of retyping
it. The snippet is JavaScript because that is where the event is built;
keeping it as a Python string means one definition reaches every probe
without a build step.

Scope note (C-1651): this pairing - the space bar and ``'Space'`` - is
where the mistake recurs, and it is what this module owns. Probes that
send a code which is not derivable from the key (``'KeyR'``, the pad's
own table, the remap probe's deliberate mismatch) are a different thing
and are not migrated here.
"""

from __future__ import annotations

#: The shared branch, as a JS function. Accepts either spelling of the
#: space bar - ``' '`` or ``'Space'`` - and returns the pair a browser
#: would send, so a probe cannot get the halves the wrong way round by
#: writing the argument the other way.
#:
#: ``preventDefault``/``stopImmediatePropagation`` are here because every
#: listener in the templates calls one or both, and a probe that omitted
#: them would throw rather than measure.
KEY_EVENT_JS = """
/* C-1651: the one place that pairs a key with its code. */
function probeKey(k){
  const key = k === 'Space' ? ' ' : k;
  return { key: key, code: key === ' ' ? 'Space' : key,
    preventDefault(){}, stopImmediatePropagation(){} } }
""".strip()

#: What the snippet introduces, so a probe that already had a ``probeKey``
#: of its own would be caught rather than silently shadowed - the same
#: contract ``PREAMBLE_NAMES`` keeps for the animation preamble.
KEY_EVENT_NAMES: tuple[str, ...] = ("probeKey",)

#: The placeholder a probe writes where the snippet goes.
KEY_EVENT_SLOT = "PROBE_KEYS_PLACEHOLDER"


def with_probe_keys(source: str) -> str:
    """Put the shared branch into a probe that asked for it."""

    return source.replace(KEY_EVENT_SLOT, KEY_EVENT_JS)


__all__ = ["KEY_EVENT_JS", "KEY_EVENT_NAMES", "KEY_EVENT_SLOT", "with_probe_keys"]
