"""Does the puzzle enforce the rules its own docstring calls its honesty?

``puzzle.py`` states what keeps SameGame a puzzle rather than a clicker: a
group is only poppable at two or more, the board collapses down and then
left, the game ends when no group of two remains, and the end screen says
whether the board was **cleared** - because 「no moves left」 and 「solved」 are
different outcomes and a page that congratulated both would be the same class
of lie the summary guard exists to prevent.

Five judges already watch this template, and none of them watches those four.
``creation_puzzle_tween`` sees the fall, ``creation_puzzle_economy`` sees big
clears buying survival, ``creation_puzzle_combo`` sees the run,
``creation_puzzle_jam_recap`` sees the sentence that says why you are stuck,
and ``creation_puzzle_hammer_endgame`` sees the comeback tool. All of them sit
*on top of* the rules; the rules themselves were unwatched.

§34 事実 1 gives the shape: a rule that does not refuse is not a rule. As in
C-1887, the board is a data structure, so this needs no player - the grid is
set directly and the page's own ``pop()`` is called.

**The end screen's two sentences are read off the page, never written here.**
A judge carrying its own copy of 「全部消えた。」 stays green against a page that
has started saying something else (C-1640, and C-1888 for the same reason one
cycle ago).

**The hammer is left to its own judge.** It is a second route through the same
branch - one lone tile broken with a tool - and measuring it here would put
two judges over one behaviour. Everything below runs at zero hammers, which is
the bare rule.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from sidra_ai.creation.games import generate_game
from sidra_ai.creation.probekeys import KEY_EVENT_JS

#: The rules, in the order the judge reports them.
RULES: tuple[tuple[str, str], ...] = (
    ("two_or_more", "2 個未満は消せない／2 個の組は消える"),
    ("collapse", "下へ詰んで、空いた列は左へ寄る"),
    ("ends_when_jammed", "組が残れば続き、無くなれば終わる"),
    ("clear_is_not_jam", "「全部消えた」と「もう消せる手がない」が別の文"),
)

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)

_PROBE = KEY_EVENT_JS + """
const _drawn = [];
let _font = '';
const _ctx = new Proxy({ fillText: (t) => { _drawn.push(String(t)) },
                         measureText: () => ({ width: 10 }) }, {
  get: (o, k) => (k in o ? o[k] : (k === 'canvas'
    ? { width: 720, height: 320 } : (typeof k === 'string' ? () => {} : undefined))),
  set: () => true });
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
let F = 0;
globalThis.performance = { now: () => F * 16 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => _ctx }) };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
function _probeFrame(){ if (queued) { const fn = queued; queued = null; fn((F++) * 16) } }
/* A board written straight in, so each rule is asked one question. -1 is
   empty; every other number is a colour the page already knows. */
function _probeSet(rowsTopDown){
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    grid[y][x] = (rowsTopDown[y] && rowsTopDown[y][x] !== undefined)
      ? rowsTopDown[y][x] : -1;
    offY[y][x] = 0; offX[y][x] = 0 }
  state = 'play'; cleared = false; hammers = 0; score = 0 }
function _probeGrid(){ return grid.map(r => r.slice()) }
function _probeTap(x, y){ cur.x = x; cur.y = y; pop(); settle() }

const out = { rows: ROWS, cols: COLS };

/* --- a lone tile, no hammer: nothing may move --- */
const lone = []; for (let y = 0; y < ROWS; y++) lone.push([]);
lone[ROWS - 1][0] = 0;
lone[ROWS - 1][2] = 1; lone[ROWS - 1][3] = 1;
_probeSet(lone);
let before = _probeGrid(), scoreBefore = score;
_probeTap(0, ROWS - 1);
out.lone = { same: JSON.stringify(_probeGrid()) === JSON.stringify(before),
             scoreMoved: score !== scoreBefore, state: state };

/* --- a pair: it goes --- */
_probeSet(lone);
before = _probeGrid(); scoreBefore = score;
_probeTap(2, ROWS - 1);
out.pair = { gone: grid[ROWS - 1][2] < 0 && grid[ROWS - 1][3] < 0,
             scoreMoved: score !== scoreBefore };

/* --- down, on its own. Every column from 0 to 3 keeps a tile, so nothing
       can shift sideways and the only thing under test is the fall. The
       first board written here left column 1 empty, the emptied-column rule
       fired as well, and the probe read the answer to a question it had not
       asked - the same lesson as C-1887's two locks in one test. --- */
const tower = []; for (let y = 0; y < ROWS; y++) tower.push([]);
tower[ROWS - 1][0] = 0;
tower[ROWS - 1][1] = 3;
tower[ROWS - 1][2] = 1; tower[ROWS - 2][2] = 1;   /* the pair, column 2 */
tower[ROWS - 3][2] = 2;                            /* riding on top */
tower[ROWS - 1][3] = 3;
_probeSet(tower);
_probeTap(2, ROWS - 1);
out.fell = { landed: grid[ROWS - 1][2], above: grid[ROWS - 2][2],
             neighbourStayed: grid[ROWS - 1][3] };

/* --- left, on its own. Column 2 holds nothing but the pair, so taking it
       empties the column and the one to its right has to close up. --- */
const gapper = []; for (let y = 0; y < ROWS; y++) gapper.push([]);
gapper[ROWS - 1][0] = 0;
gapper[ROWS - 1][1] = 3;
gapper[ROWS - 1][2] = 1; gapper[ROWS - 2][2] = 1;  /* the pair, alone */
gapper[ROWS - 1][3] = 4;                            /* must move into 2 */
_probeSet(gapper);
_probeTap(2, ROWS - 1);
out.closed = { atTwo: grid[ROWS - 1][2], atThree: grid[ROWS - 1][3] };

/* --- the end: a board with one pair is still in play; take it and the game
       is over with nothing left, which is a CLEAR, not a jam --- */
const last = []; for (let y = 0; y < ROWS; y++) last.push([]);
last[ROWS - 1][0] = 0; last[ROWS - 1][1] = 0;
_probeSet(last);
out.beforeLast = { state: state, moves: movesLeft() };
_probeTap(0, ROWS - 1);
_drawn.length = 0; draw(0);
out.cleared = { state: state, cleared: cleared, said: _drawn.slice() };

/* --- a jam: two lone tiles of different colours, nothing poppable --- */
const jammed = []; for (let y = 0; y < ROWS; y++) jammed.push([]);
jammed[ROWS - 1][0] = 0; jammed[ROWS - 1][1] = 1;
jammed[ROWS - 1][3] = 2; jammed[ROWS - 1][4] = 2;
_probeSet(jammed);
_probeTap(3, ROWS - 1);
_drawn.length = 0; draw(0);
out.jammed = { state: state, cleared: cleared, said: _drawn.slice(), moves: movesLeft() };
console.log(JSON.stringify(out));
"""


@dataclass(frozen=True)
class PuzzleRulesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    held: int = 0
    rules: tuple[str, ...] = ()


def _drive() -> dict | None:
    page = generate_game("パズルゲームを作って", template="puzzle").html
    script = _SCRIPT.search(page)
    if script is None:
        return None
    try:
        run = subprocess.run(
            ["node", "-"],
            input=_PROBE.replace("SCRIPT_PLACEHOLDER", script.group(1)),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if run.returncode != 0:
            return None
        return json.loads(run.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def evaluate_puzzle_rules_hold() -> PuzzleRulesResult:
    checks = 0
    failures: list[str] = []
    held: list[str] = []

    seen = _drive()
    if seen is None:
        return PuzzleRulesResult(False, 0, 1, ("運転器が動かせない",))

    def rule(key: str, refuses: bool, allows: bool, why: str) -> None:
        nonlocal checks
        if refuses:
            checks += 1
        else:
            failures.append(f"{key}: 規則が拒まない（{why}）")
        if allows:
            checks += 1
        else:
            failures.append(f"{key}: 規則どおりでも通らない（{why}）")
        if refuses and allows:
            held.append(key)

    lone, pair = seen.get("lone") or {}, seen.get("pair") or {}
    rule(
        "two_or_more",
        bool(lone.get("same")) and not lone.get("scoreMoved"),
        bool(pair.get("gone")) and bool(pair.get("scoreMoved")),
        "1 個は消えず、2 個は消える",
    )

    fell, closed = seen.get("fell") or {}, seen.get("closed") or {}
    # Two boards, one question each. Down: the tile that rode on the pair
    # lands on the floor, its old square empties, and nothing shifts
    # sideways because no column emptied. Left: the column that DID empty
    # closes up and its neighbour moves in.
    rule(
        "collapse",
        fell.get("above") == -1 and fell.get("neighbourStayed") == 3,
        fell.get("landed") == 2 and closed.get("atTwo") == 4
        and closed.get("atThree") == -1,
        "落ちるべきものは落ち、空いた列だけが左へ寄る",
    )

    before, cleared = seen.get("beforeLast") or {}, seen.get("cleared") or {}
    rule(
        "ends_when_jammed",
        before.get("state") == "play" and bool(before.get("moves")),
        cleared.get("state") == "over",
        "組が残れば続き、無くなれば終わる",
    )

    jam = seen.get("jammed") or {}
    said_clear = " ".join(cleared.get("said") or [])
    said_jam = " ".join(jam.get("said") or [])
    # Both screens have to speak, and they have to say different things. The
    # words are the page's; this only asks that they differ and that the
    # cleared one is the board that really emptied.
    rule(
        "clear_is_not_jam",
        bool(said_jam) and not jam.get("cleared") and said_jam != said_clear,
        bool(said_clear) and bool(cleared.get("cleared")),
        "全消しと詰みで違う文",
    )

    want = len(RULES)
    if len(held) == want:
        checks += 1
    else:
        failures.append(f"{len(held)}/{want} の規則しか両方向で確かめていない")

    return PuzzleRulesResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
        held=len(held),
        rules=tuple(held),
    )


__all__ = ["RULES", "PuzzleRulesResult", "evaluate_puzzle_rules_hold"]
