"""Procedural low-poly 3D models, written as plain Wavefront OBJ text.

Everything here is deterministic arithmetic: a shape is chosen from the
request's own words, a seed is derived from the request, and the geometry is
built from parametric primitives with seeded jitter. No mesh library, no
model download, no network. The OBJ/MTL pair opens in the Windows 3D Viewer
as-is, and the preview page renders the same triangles with a small canvas
software rasteriser - self-contained, no CDN, no WebGL context to be denied.

The palette is GAMEYARD's own (site docs/DESIGN.md): dark foundation, cyan
primary, magenta as a small accent. It is baked into the MTL rather than
sampled from anywhere at run time.
"""

from __future__ import annotations

import math
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from random import Random

from sidra_ai.creation.games import _javascript_parses, _no_external_assets, _script_of

# GAMEYARD tokens as linear-ish RGB triples for MTL diffuse colours.
_PALETTE: dict[str, tuple[float, float, float]] = {
    "gy_cyan": (0.180, 0.902, 1.000),      # #2ee6ff
    "gy_dark": (0.039, 0.059, 0.133),      # #0a0f1c
    "gy_magenta": (1.000, 0.361, 0.784),   # #ff5cc8
}
_MATERIAL_ORDER = ("gy_cyan", "gy_dark", "gy_magenta")

_FISH_WORDS = ("魚", "さかな", "フィッシュ", "fish", "釣り")
_BOAT_WORDS = ("舟", "船", "ボート", "boat", "ship")
_TERRAIN_WORDS = ("地形", "島", "山", "terrain", "island", "ステージ")

_STRIP = re.compile(
    r"(の)?(3d|３d)?\s*(モデル|model|obj)?(を|で)?(作って|作成して|生成して|つくって|ください|下さい)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeneratedModel3D:
    """One generated model: geometry text plus its provenance."""

    shape: str
    title: str
    seed: int
    obj_text: str
    mtl_text: str
    preview_html: str
    vertex_count: int
    face_count: int
    evidence: tuple[str, ...] = field(default_factory=tuple)


def choose_shape(request: str) -> str:
    """Pick by what the request names; the fish is the flagship default."""

    lowered = request.lower()
    if any(word in lowered for word in _BOAT_WORDS):
        return "boat"
    if any(word in lowered for word in _TERRAIN_WORDS):
        return "terrain"
    if any(word in lowered for word in _FISH_WORDS):
        return "fish"
    return "fish"


def _title_from(request: str, fallback: str) -> str:
    stripped = _STRIP.sub("", request.strip()).strip("「」\"' 　")
    if 1 <= len(stripped) <= 24:
        return stripped
    return fallback


# ----------------------------------------------------------------- geometry
#
# A mesh is (vertices, faces): vertices are (x, y, z) floats, faces are
# (i, j, k, material) with 0-based indices into the vertex list. Everything
# is triangles so the preview rasteriser and the OBJ writer share one shape
# of data.

Mesh = tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]]


def _lathe(profile: list[tuple[float, float, float]], sides: int, material: int) -> Mesh:
    """Sweep elliptical cross-sections along the x axis.

    ``profile`` rows are (x, ry, rz). A radius of zero collapses the ring to
    one point, which is how the fish gets a nose and a tail root without
    special cases.
    """

    vertices: list[tuple[float, float, float]] = []
    rings: list[list[int]] = []
    for x, ry, rz in profile:
        ring: list[int] = []
        if ry <= 0 and rz <= 0:
            ring = [len(vertices)]
            vertices.append((x, 0.0, 0.0))
        else:
            for s in range(sides):
                angle = 2 * math.pi * s / sides
                ring.append(len(vertices))
                vertices.append((x, ry * math.cos(angle), rz * math.sin(angle)))
        rings.append(ring)

    faces: list[tuple[int, int, int, int]] = []
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for s in range(len(b)):
                faces.append((a[0], b[s], b[(s + 1) % len(b)], material))
        elif len(b) == 1:
            for s in range(len(a)):
                faces.append((a[s], a[(s + 1) % len(a)], b[0], material))
        else:
            for s in range(len(a)):
                s2 = (s + 1) % len(a)
                faces.append((a[s], a[s2], b[s], material))
                faces.append((a[s2], b[s2], b[s], material))
    return vertices, faces


def _merge(*meshes: Mesh) -> Mesh:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for mesh_vertices, mesh_faces in meshes:
        offset = len(vertices)
        vertices.extend(mesh_vertices)
        faces.extend((i + offset, j + offset, k + offset, m) for i, j, k, m in mesh_faces)
    return vertices, faces


def _fin(points: list[tuple[float, float, float]], material: int) -> Mesh:
    """A flat fan of triangles; both windings so it shows from either side."""

    faces = []
    for i in range(1, len(points) - 1):
        faces.append((0, i, i + 1, material))
        faces.append((0, i + 1, i, material))
    return list(points), faces


def _fish(rng: Random) -> Mesh:
    length = 1.0 * (0.9 + 0.2 * rng.random())
    height = 0.28 * (0.85 + 0.3 * rng.random())
    width = height * 0.62
    body = _lathe(
        [
            (-length, 0.0, 0.0),
            (-length * 0.72, height * 0.35, width * 0.35),
            (-length * 0.25, height * 0.9, width * 0.9),
            (length * 0.15, height, width),
            (length * 0.6, height * 0.62, width * 0.62),
            (length * 0.95, height * 0.2, width * 0.2),
            (length, 0.0, 0.0),
        ],
        sides=8,
        material=0,
    )
    tail = _fin(
        [
            (-length * 0.98, 0.0, 0.0),
            (-length * 1.35, height * 1.15, 0.0),
            (-length * 1.18, 0.0, 0.0),
            (-length * 1.35, -height * 1.15, 0.0),
        ],
        material=2,
    )
    dorsal = _fin(
        [
            (-length * 0.1, height * 0.92, 0.0),
            (length * 0.05, height * 1.5, 0.0),
            (length * 0.3, height * 0.95, 0.0),
        ],
        material=2,
    )
    return _merge(body, tail, dorsal)


def _boat(rng: Random) -> Mesh:
    length = 1.1 * (0.9 + 0.2 * rng.random())
    beam = 0.34 * (0.9 + 0.2 * rng.random())
    depth = 0.26
    stations = [
        (-length, 0.0, 0.0),
        (-length * 0.6, depth * 0.8, beam * 0.7),
        (0.0, depth, beam),
        (length * 0.6, depth * 0.8, beam * 0.7),
        (length, 0.0, 0.0),
    ]
    # The hull is a lathe squashed later: build with ry=depth, rz=beam and
    # keep only the lower half by flattening y above deck level to the deck.
    vertices, faces = _lathe([(x, ry, rz) for x, ry, rz in stations], sides=8, material=1)
    deck_y = depth * 0.35
    vertices = [(x, min(y, deck_y), z) for x, y, z in vertices]
    # Cyan gunwale: retag faces whose every vertex sits at deck height.
    retagged = []
    for i, j, k, m in faces:
        at_deck = all(abs(vertices[idx][1] - deck_y) < 1e-9 for idx in (i, j, k))
        retagged.append((i, j, k, 0 if at_deck else m))
    return vertices, retagged


def _terrain(rng: Random) -> Mesh:
    n = 9
    bumps = [
        (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0.18, 0.4), rng.uniform(0.25, 0.5))
        for _ in range(3)
    ]

    def height(x: float, z: float) -> float:
        total = 0.0
        for bx, bz, amplitude, spread in bumps:
            d2 = (x - bx) ** 2 + (z - bz) ** 2
            total += amplitude * math.exp(-d2 / (2 * spread**2))
        return total

    vertices: list[tuple[float, float, float]] = []
    for row in range(n):
        for col in range(n):
            x = -1.0 + 2.0 * col / (n - 1)
            z = -1.0 + 2.0 * row / (n - 1)
            vertices.append((x, height(x, z), z))
    peak = max(v[1] for v in vertices) or 1.0
    faces: list[tuple[int, int, int, int]] = []
    for row in range(n - 1):
        for col in range(n - 1):
            a = row * n + col
            b = a + 1
            c = a + n
            d = c + 1
            for tri in ((a, c, b), (b, c, d)):
                top = max(vertices[idx][1] for idx in tri)
                material = 0 if top > peak * 0.55 else 1
                faces.append((*tri, material))
    return vertices, faces


_SHAPES = {"fish": _fish, "boat": _boat, "terrain": _terrain}
_SHAPE_TITLES = {"fish": "魚", "boat": "舟", "terrain": "地形"}


# ------------------------------------------------------------------- output


def _obj_text(mesh: Mesh) -> str:
    vertices, faces = mesh
    lines = ["# SIDRA AI procedural model", "mtllib model.mtl"]
    for x, y, z in vertices:
        lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
    for material_index, material in enumerate(_MATERIAL_ORDER):
        block = [f for f in faces if f[3] == material_index]
        if not block:
            continue
        lines.append(f"usemtl {material}")
        for i, j, k, _ in block:
            lines.append(f"f {i + 1} {j + 1} {k + 1}")
    return "\n".join(lines) + "\n"


def _mtl_text() -> str:
    lines = ["# GAMEYARD palette (site docs/DESIGN.md)"]
    for name in _MATERIAL_ORDER:
        r, g, b = _PALETTE[name]
        lines += [f"newmtl {name}", f"Kd {r:.3f} {g:.3f} {b:.3f}", "Ks 0.05 0.05 0.05", "d 1.0"]
    return "\n".join(lines) + "\n"


def _preview_html(title: str, mesh: Mesh, evidence: tuple[str, ...]) -> str:
    vertices, faces = mesh
    verts_js = ",".join(f"[{x:.4f},{y:.4f},{z:.4f}]" for x, y, z in vertices)
    faces_js = ",".join(f"[{i},{j},{k},{m}]" for i, j, k, m in faces)
    sources = "".join(f"<li>{escape(line)}</li>" for line in evidence)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} - SIDRA 3D preview</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;background:#05070f;color:#e6f7ff;font-family:system-ui,sans-serif;
display:flex;flex-direction:column;align-items:center;gap:12px;padding:24px}}
canvas{{background:#0a0f1c;border-radius:12px;max-width:100%}}
h1{{font-size:1.1rem;margin:0}}
small,li{{color:#8fb3c7}}
ul{{margin:0;padding-left:1.2em}}
</style></head><body>
<h1>{escape(title)}</h1>
<canvas id="c" width="640" height="480"></canvas>
<small id="note">ドラッグ不要・自動回転（reduced-motion 設定では静止します）。
.obj は Windows の 3D ビューアーで開けます。</small>
<ul>{sources}</ul>
<script>
"use strict";
var VERTS=[{verts_js}];
var FACES=[{faces_js}];
var COLORS=[[46,230,255],[10,15,28],[255,92,200]];
var canvas=document.getElementById("c");
var ctx=canvas.getContext("2d");
var reduced=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function render(angle){{
  var w=canvas.width,h=canvas.height;
  ctx.fillStyle="#0a0f1c";ctx.fillRect(0,0,w,h);
  var ca=Math.cos(angle),sa=Math.sin(angle);
  var tilt=0.35,ct=Math.cos(tilt),st=Math.sin(tilt);
  var pts=[];
  for(var v=0;v<VERTS.length;v++){{
    var x=VERTS[v][0],y=VERTS[v][1],z=VERTS[v][2];
    var rx=x*ca+z*sa, rz=-x*sa+z*ca;
    var ry=y*ct-rz*st, rz2=y*st+rz*ct+3.2;
    var s=Math.min(w,h)*0.62/rz2;
    pts.push([w/2+rx*s,h/2-ry*s,rz2]);
  }}
  var order=[];
  for(var f=0;f<FACES.length;f++){{
    var a=pts[FACES[f][0]],b=pts[FACES[f][1]],c=pts[FACES[f][2]];
    order.push([f,(a[2]+b[2]+c[2])/3]);
  }}
  order.sort(function(p,q){{return q[1]-p[1];}});
  for(var o=0;o<order.length;o++){{
    var face=FACES[order[o][0]];
    var a=pts[face[0]],b=pts[face[1]],c=pts[face[2]];
    var cross=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    if(cross<=0)continue;
    var depth=order[o][1];
    var shade=Math.max(0.35,Math.min(1,1.45-depth/3.4));
    var col=COLORS[face[3]];
    ctx.fillStyle="rgb("+Math.round(col[0]*shade)+","+Math.round(col[1]*shade)+","+Math.round(col[2]*shade)+")";
    ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(c[0],c[1]);
    ctx.closePath();ctx.fill();
  }}
}}
if(reduced){{render(0.7);}}
else{{
  var angle=0;
  (function tick(){{angle+=0.012;render(angle);window.requestAnimationFrame(tick);}})();
}}
</script></body></html>
"""


def generate_model3d(
    request: str,
    *,
    shape: str | None = None,
    seed: int | None = None,
    evidence: list[str] | None = None,
) -> GeneratedModel3D:
    """Build one model deterministically from the request text."""

    chosen = shape or choose_shape(request)
    if chosen not in _SHAPES:
        raise ValueError(f"unknown shape {chosen!r}")
    actual_seed = zlib.crc32(request.encode("utf-8")) if seed is None else seed
    mesh = _SHAPES[chosen](Random(actual_seed))
    title = _title_from(request, _SHAPE_TITLES[chosen])
    trail = tuple(evidence or ()) or ("palette: tukemen-rgb/site docs/DESIGN.md",)
    return GeneratedModel3D(
        shape=chosen,
        title=title,
        seed=actual_seed,
        obj_text=_obj_text(mesh),
        mtl_text=_mtl_text(),
        preview_html=_preview_html(title, mesh, trail),
        vertex_count=len(mesh[0]),
        face_count=len(mesh[1]),
        evidence=trail,
    )


def save_model3d(
    model: GeneratedModel3D, data_dir: str | Path, *, now: datetime | None = None
) -> dict[str, Path]:
    """Write obj/mtl/preview next to each other. Nothing leaves the machine."""

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory = Path(data_dir) / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"model3d-{model.shape}-{stamp}"
    obj_path = directory / f"{stem}.obj"
    mtl_path = directory / f"{stem}.mtl"
    preview_path = directory / f"{stem}-preview.html"
    obj_path.write_text(
        model.obj_text.replace("mtllib model.mtl", f"mtllib {mtl_path.name}", 1),
        encoding="utf-8",
    )
    mtl_path.write_text(model.mtl_text, encoding="utf-8")
    preview_path.write_text(model.preview_html, encoding="utf-8")
    return {"obj": obj_path, "mtl": mtl_path, "preview": preview_path}


# ---------------------------------------------------------------- validation


def validate_model3d(model: GeneratedModel3D) -> dict:
    """Report every reason the model would not open or preview, not the first."""

    failures: list[str] = []
    vertex_count = 0
    face_lines = 0
    seen_mtllib = False
    seen_usemtl = 0
    for line in model.obj_text.splitlines():
        if line.startswith("v "):
            vertex_count += 1
        elif line.startswith("mtllib "):
            seen_mtllib = True
        elif line.startswith("usemtl "):
            seen_usemtl += 1
        elif line.startswith("f "):
            face_lines += 1
            for token in line.split()[1:]:
                index = int(token.split("/")[0])
                if not (1 <= index <= max(vertex_count, 1)):
                    failures.append(f"face index {index} out of range")
                    break
    if vertex_count == 0:
        failures.append("no vertices")
    if face_lines == 0:
        failures.append("no faces")
    if not seen_mtllib:
        failures.append("no mtllib reference")
    if seen_usemtl == 0:
        failures.append("no usemtl")
    if "newmtl" not in model.mtl_text or "Kd " not in model.mtl_text:
        failures.append("mtl has no material with a diffuse colour")

    script = _script_of(model.preview_html)
    checker = "not run"
    if "<canvas" not in model.preview_html:
        failures.append("preview has no <canvas>")
    if not script.strip():
        failures.append("preview has no <script>")
    else:
        parses, checker = _javascript_parses(script)
        if not parses:
            failures.append(f"preview javascript did not parse ({checker})")
    if not _no_external_assets(model.preview_html):
        failures.append("preview references an external asset")
    if "prefers-reduced-motion" not in model.preview_html:
        failures.append("preview ignores prefers-reduced-motion")

    return {
        "valid": not failures,
        "failures": failures,
        "js_checker": checker,
        "vertices": vertex_count,
        "faces": face_lines,
    }


__all__ = [
    "GeneratedModel3D",
    "choose_shape",
    "generate_model3d",
    "save_model3d",
    "validate_model3d",
]
