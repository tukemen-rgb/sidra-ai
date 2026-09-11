"""Shared pieces for the probes that drive real pages (C-1651, C-1652).

A probe is an instrument. When one is written from memory each time, the
same slip comes back: twice in one session a probe built its key events as
``code: k``, which sends ``code: ' '`` for the space bar. Both times the
probe still appeared to work - the page under it happened to listen on
``e.key``, or the probe only ever pressed a letter - so nothing but a
repo-wide source scan noticed. A scan catches the repeat; it does not stop
it. The snippet below does, by being the only place the rule is written.
"""

from __future__ import annotations

#: A synthesised keyboard event, built the way the pages actually read it.
#: The templates are split: some test ``e.key``, some test ``e.code``, and
#: for the space bar those two differ (``' '`` against ``'Space'``). Any
#: probe that presses a key should embed this rather than hand-roll it.
PROBE_KEYS = """
function probeKey(type, k, handlers){
  let stopped = false;
  const e = { key: k, code: k === ' ' ? 'Space' : k,
    preventDefault(){}, stopImmediatePropagation(){ stopped = true } };
  for (const fn of (handlers[type] || [])) { fn(e); if (stopped) break }
  return e }
"""

#: Read one frame's own camera kick, not the history of every kick before
#: it (C-1648). ``shake()`` keeps ``Math.max`` and decays it by 0.78 each
#: frame, so a heavy event a few frames back sits on top of a light one and
#: inverts the ladder. Clearing the accumulator before each frame is the
#: probe's own view; the page is untouched.
PROBE_SHAKE = """
function probeKick(step){
  SHAKE = 0;
  step();
  return shakeAmount() }
"""

__all__ = ["PROBE_KEYS", "PROBE_SHAKE"]
