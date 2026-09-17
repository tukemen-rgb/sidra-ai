"""Does the 3D preview actually show the model, all the way round?

The preview is the artifact an operator opens and forwards - the .obj is
a file, this is the picture of it. §4 is the readable-screen minimum, and
its judges so far measure text contrast (C-1329) and the virtual pad's
non-text contrast; nobody had asked the plainer question underneath them:
**is anything drawn at all?**

It was not. The renderer culls back faces, which is right for a closed
solid - the half turned away is the inside, and drawing it lets the
viewer see through the fish. The terrain is not a closed solid: it is a
9x9 heightfield, an open sheet with no inside to hide. Culled, it drew 0
to 17 of its 128 faces (median 5) and was **completely blank at 27 of 120
angles** - more than a fifth of every turn showing nothing.

So this drives the page through a **whole revolution** and counts the
faces it really paints at each angle. Four directions, because each of
the obvious wrong fixes passes the others:

  (a) nothing is ever blank - at every angle of the turn, every shape
      paints something;
  (b) an open surface shows all of itself, because there is no half of it
      that should be hidden;
  (c) a closed solid still hides its inside - it must NOT paint every
      face, or the fix was "turn culling off", which makes a solid
      transparent while satisfying (a) and (b);
  (d) and open-versus-closed is decided **here, from the geometry of the
      .obj the operator downloads** - not by a list of names and not by
      asking the page. The page carries its own `TWOSIDED` flag; taking
      that as the truth would let a page that mislabels itself pick which
      rule it is judged by, and sabotage D2 (two-sided for everything)
      escaped the closed-solid rule exactly that way before this was
      turned round. The flag is compared against the geometry instead.
      Checked across the product's own `_SHAPES` registry (C-1887,
      C-1891, C-1894).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

#: Angles sampled over one full turn.
STEPS = 120

#: What share of its faces a CLOSED solid must still show. The culled half
#: is correct, so this is well under half; it is here to catch a solid
#: that has stopped drawing, not to pin the exact share.
CLOSED_FLOOR = 0.2

#: And what share it must NOT reach, because a closed solid that paints
#: every face is one you can see through.
CLOSED_CEILING = 0.95

_PROBE = """
const nothing = new Proxy(function(){}, {
  get:(t,k)=>(k===Symbol.toPrimitive?()=>0:nothing), apply:()=>nothing, set:()=>true });
globalThis.matchMedia = () => ({ matches: false });
globalThis.window = globalThis;
let NOW = 0;
globalThis.performance = { now: () => NOW };
globalThis.addEventListener = () => {};
/* One count per painted face: the renderer opens each with moveTo. */
let N = 0;
const rec = new Proxy(function(){}, {
  get:(t,k)=>{ if(k==='moveTo') return ()=>{ N++ };
    if(k===Symbol.toPrimitive) return ()=>0; return nothing },
  set:()=>true, apply:()=>nothing });
const _canvas = { width:640, height:480, style:{}, addEventListener:()=>{},
  getBoundingClientRect:()=>({left:0,top:0,width:640,height:480}),
  getContext: () => rec };
globalThis.document = { getElementById: () => _canvas, querySelector: () => _canvas };
globalThis.requestAnimationFrame = () => 1;
SCRIPT_PLACEHOLDER
const STEPS = STEPS_PLACEHOLDER;
const drawn = [];
for (let i=0;i<STEPS;i++){ N=0; render(i*Math.PI*2/STEPS); drawn.push(N) }
console.log(JSON.stringify({ faces: FACES.length, twoSided: TWOSIDED, drawn: drawn }));
"""


@dataclass(frozen=True)
class PreviewShowsResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()


def build_probe(script: str) -> str:
    return _PROBE.replace("SCRIPT_PLACEHOLDER", script).replace(
        "STEPS_PLACEHOLDER", str(STEPS)
    )


def _run(job: tuple[str, str]) -> tuple[str, dict | str]:
    shape, script = job
    from sidra_ai.evals.scratch import scratch_dir

    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, dir=str(scratch_dir()), encoding="utf-8"
    ) as handle:
        handle.write(build_probe(script))
        path = handle.name
    try:
        done = subprocess.run(
            ["node", path], capture_output=True, text=True, timeout=120
        )
        if done.returncode != 0:
            return shape, f"node exited {done.returncode}: {done.stderr[-200:]}"
        return shape, json.loads(done.stdout.strip().splitlines()[-1])
    except Exception as err:  # a probe that cannot run is a failure, not a pass
        return shape, f"{type(err).__name__}: {err}"
    finally:
        os.unlink(path)


def evaluate_model3d_preview_shows_the_model() -> PreviewShowsResult:
    from sidra_ai.creation.models3d import _has_boundary, _SHAPES, generate_model3d

    failures: list[str] = []
    readings: list[str] = []
    checks = 0

    shapes = tuple(sorted(_SHAPES))
    if not shapes:
        return PreviewShowsResult(False, 0, 1, ("the product lists no shapes at all",))

    # (d) the table has to contain both kinds, or the two halves of the rule
    # are never both exercised - and the answer has to come from the mesh.
    open_shapes, closed_shapes = [], []
    is_open: dict[str, bool] = {}
    for shape in shapes:
        built = generate_model3d("3Dモデルを作って", shape=shape)
        is_open[shape] = _has_boundary(
            ([(0.0, 0.0, 0.0)] * built.vertex_count, _mesh_faces(built))
        )
        (open_shapes if is_open[shape] else closed_shapes).append(shape)
    if not open_shapes or not closed_shapes:
        failures.append(
            "the shapes must include both an open surface and a closed solid - "
            f"open={open_shapes or 'none'}, closed={closed_shapes or 'none'}"
        )
    else:
        checks += 1

    jobs: list[tuple[str, str]] = []
    for shape in shapes:
        html = generate_model3d("3Dモデルを作って", shape=shape).preview_html
        found = re.search(r"<script>(.*?)</script>", html, re.S)
        if not found:
            failures.append(f"{shape}: the preview page carries no script")
            continue
        jobs.append((shape, found.group(1)))

    runs: dict[str, dict | str] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for shape, out in pool.map(_run, jobs):
            runs[shape] = out

    for shape in shapes:
        out = runs.get(shape)
        if isinstance(out, str) or out is None:
            failures.append(f"{shape}: {out or 'did not run'}")
            continue
        drawn = out.get("drawn") or []
        faces = out.get("faces") or 0
        if not drawn or not faces:
            failures.append(f"{shape}: the probe read no faces at all")
            continue

        # (a) never blank
        blank = sum(1 for n in drawn if n == 0)
        if blank:
            failures.append(
                f"{shape}: blank at {blank} of {len(drawn)} angles "
                f"({blank * 100 / len(drawn):.0f}% of the turn shows nothing)"
            )
        else:
            checks += 1

        least, most = min(drawn), max(drawn)

        # The page's own flag, against the geometry. The page does not get
        # to choose which rule it is measured by.
        if bool(out.get("twoSided")) != is_open[shape]:
            failures.append(
                f"{shape}: the page says twoSided={out.get('twoSided')} but its "
                f".obj is {'open' if is_open[shape] else 'closed'}"
            )
        else:
            checks += 1

        if is_open[shape]:
            # (b) an open sheet has no half to hide
            if least < faces:
                failures.append(
                    f"{shape} (open): shows {least} of its {faces} faces at its "
                    "worst angle - an open surface has no inside to cull"
                )
            else:
                checks += 1
        else:
            # (c) a closed solid still hides its inside, and still shows some
            if most > faces * CLOSED_CEILING:
                failures.append(
                    f"{shape} (closed): paints {most} of {faces} faces - a solid "
                    "that draws its inside is one you can see through"
                )
            elif least < faces * CLOSED_FLOOR:
                failures.append(
                    f"{shape} (closed): only {least} of {faces} faces at its "
                    "worst angle"
                )
            else:
                checks += 1
        readings.append(
            f"{shape}{'（開）' if is_open[shape] else '（閉）'} "
            f"{least}〜{most}/{faces}・空白 {blank}/{len(drawn)}"
        )

    return PreviewShowsResult(
        passed=not failures,
        checks_passed=checks,
        checks_total=checks + len(failures),
        failures=tuple(failures),
        readings=tuple(readings),
    )


def _mesh_faces(built) -> list[tuple[int, int, int, int]]:
    """The faces of a built model, read back out of the .obj it ships.

    Read from the artifact rather than from the generator's own mesh, so
    the classification is checked against what the operator downloads.
    """

    faces: list[tuple[int, int, int, int]] = []
    for line in built.obj_text.splitlines():
        if not line.startswith("f "):
            continue
        idx = [int(part.split("/")[0]) - 1 for part in line.split()[1:]]
        if len(idx) >= 3:
            faces.append((idx[0], idx[1], idx[2], 0))
    return faces
