"""Make a playable single-file game, with no model and no network.

"釣りゲームを作って" has to produce something that actually runs, on this
container, in the echo configuration, with no weights present. So the game is
a **template** first: the HTML, the loop and the rules are written here and are
correct before any model is consulted. A local model, when there is one, only
fills copy - title and one line of flavour - and only through
``GeneratedGame.with_copy``. That ordering is the whole design: a missing model
costs the page its wording, never its playability.

Three constraints the output has to satisfy, all checkable:

* **single file, no network.** No CDN font, no external script, no image URL.
  The operator's machine is loopback-bound; a page that fetches to work is a
  page that does nothing where it matters. ``_no_external_assets`` proves it.
* **GAMEYARD's identity, not a second design system.** The tokens below are
  copied from ``tukemen-rgb/site`` ``docs/DESIGN.md`` §2, and §3's prohibited
  defaults are respected: no purple-to-blue gradient, no glow or glassmorphism,
  no 3D buttons, no emoji as interface icons, no font CDN.
* **grounded.** Whatever the caller retrieved is printed in the page's own
  footer as the source of those tokens, so the artifact says where its
  appearance came from instead of implying taste.
"""

from __future__ import annotations

import json
import re
import subprocess
import zlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from sidra_ai.creation.adventure import (
    ADVENTURE_DIFFICULTY,
    ADVENTURE_HOW,
    ADVENTURE_SCRIPT,
    ADVENTURE_TITLE,
    ADVENTURE_WORDS,
)
from sidra_ai.creation.animation import with_animation

#: Re-exported from :mod:`sidra_ai.creation.themes`, which is where the site's
#: DESIGN.md §2 palette now lives: the default theme has to *be* these tokens
#: rather than a second copy of them, and a module that owns both cannot be
#: imported by the one that owns neither. Every existing
#: ``from ...games import GAMEYARD_TOKENS`` keeps working.
from sidra_ai.creation.themes import GAMEYARD_TOKENS, Theme, select_theme

_SOURCE = "tukemen-rgb/site docs/DESIGN.md §2 (tokens) / §3 (prohibited defaults)"


@dataclass(frozen=True)
class GameTemplate:
    """One playable rule set. ``body`` is the whole game; nothing is fetched."""

    key: str
    default_title: str
    how_to_play: str
    #: Called with the resolved difficulty; returns the game's JavaScript.
    script: str


@dataclass(frozen=True)
class GeneratedGame:
    template: str
    title: str
    tagline: str
    difficulty: str
    html: str

    def with_copy(self, *, title: str = "", tagline: str = "") -> "GeneratedGame":
        """Overlay model-written wording on a page that already works.

        Empty strings are ignored, so a model that returns nothing leaves the
        deterministic copy standing rather than blanking the page.
        """

        new_title = title.strip() or self.title
        new_tagline = tagline.strip() or self.tagline
        if (new_title, new_tagline) == (self.title, self.tagline):
            return self
        html = self.html.replace(escape(self.title), escape(new_title))
        html = html.replace(escape(self.tagline), escape(new_tagline))
        return replace(self, title=new_title, tagline=new_tagline, html=html)


# --------------------------------------------------------------- templates

_FISHING = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const SPEED=SPEED_TOKEN,BAND=BAND_TOKEN;
let pos=0,dir=1,score=0,casts=0,flash=0,msg='SPACE / クリックで合わせる';
const zone=()=>[0.5-BAND/2,0.5+BAND/2];
function step(){pos+=dir*SPEED;if(pos>1){pos=1;dir=-1}if(pos<0){pos=0;dir=1}draw();
  requestAnimationFrame(step)}
function draw(){const w=cv.width,h=cv.height,now=performance.now();cx.fillStyle='SURFACE_TOKEN';
  cx.fillRect(0,0,w,h);const [a,b]=zone();
  cx.fillStyle='RAISED_TOKEN';cx.fillRect(40,h/2-26,w-80,52);
  cx.fillStyle='CYAN_TOKEN';cx.globalAlpha=0.28;
  cx.fillRect(40+(w-80)*a,h/2-26,(w-80)*(b-a),52);cx.globalAlpha=1;
  /* decorative: a four-frame bob on the target sprite. FRAME pins it to 0
     under reduced motion, so it sits still while the game keeps running. */
  const bob=[0,-3,0,3][FRAME(4,6,now)];
  /* the catch flash eases out; ease() is the identity when reduced */
  if(flash>0){cx.globalAlpha=0.35*ease(flash);cx.fillStyle='CYAN_TOKEN';
    cx.fillRect(0,0,w,h);cx.globalAlpha=1;flash-=0.04}
  sprite('marker',40+(w-80)*pos-8,h/2-34,16,68,'MAGENTA_TOKEN');
  sprite('target',40+(w-80)*0.5-16,h/2-16+bob,32,32,'');
  cx.fillStyle='#dfe7f5';cx.font='16px ui-monospace,monospace';
  cx.fillText(msg,40,h-28);cx.fillText('釣果 '+score+' / '+casts,40,34)}
function cast(){casts++;const [a,b]=zone();
  if(pos>=a&&pos<=b){score++;flash=1;msg='かかった。'}else{msg='逃げられた。'}}
addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault();cast()}});
cv.addEventListener('pointerdown',cast);
step();
"""

_CATCH = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const FALL=SPEED_TOKEN,WIDE=BAND_TOKEN;
let px=0.5,shown=0.5,items=[],score=0,missed=0,t=0;
addEventListener('keydown',e=>{if(e.code==='ArrowLeft'){px=Math.max(0,px-0.06)}
  if(e.code==='ArrowRight'){px=Math.min(1,px+0.06)}});
cv.addEventListener('pointermove',e=>{const r=cv.getBoundingClientRect();
  px=Math.min(1,Math.max(0,(e.clientX-r.left)/r.width))});
function step(){t++;if(t%FALL===0){items.push({x:Math.random(),y:0})}
  const w=cv.width,h=cv.height;
  items.forEach(i=>{i.y+=0.012});
  items=items.filter(i=>{if(i.y<0.92)return true;
    if(Math.abs(i.x-shown)<WIDE/2){score++}else{missed++}return false});
  cx.fillStyle='SURFACE_TOKEN';cx.fillRect(0,0,w,h);
  /* the basket eases toward the pointer instead of snapping to it */
  shown+=(px-shown)*(REDUCED?1:0.25);
  /* decorative: a four-frame pulse, frozen when reduced */
  const pulse=[0,1,2,1][FRAME(4,8,performance.now())];
  items.forEach(i=>{sprite('target',i.x*w-10,i.y*h,20,20,'CYAN_TOKEN')});
  sprite('marker',(shown-WIDE/2)*w,h-30-pulse,WIDE*w,20+pulse,'MAGENTA_TOKEN');
  cx.fillStyle='#dfe7f5';cx.font='16px ui-monospace,monospace';
  cx.fillText('受け '+score+' / こぼし '+missed,40,34);
  cx.fillText('← → またはマウスで動かす',40,h-28);
  requestAnimationFrame(step)}
step();
"""


#: Sprite support, prepended to every template. With no sprites the object is
#: empty and ``sprite`` falls straight through to the rectangle the template
#: always drew, so the single-file page is byte-for-byte the game it was
#: before this existed. With sprites it still falls through until the image
#: has decoded, and permanently if the file is missing - a production whose
#: assets directory was emptied stays playable rather than blank.
_SPRITE_LOADER = """
const SPRITES=SPRITE_MAP_TOKEN,IMAGES={};
Object.keys(SPRITES).forEach(function(name){
  const img=new Image();img.src=SPRITES[name];IMAGES[name]=img});
function sprite(name,x,y,w,h,fallback){
  const img=IMAGES[name];
  if(img&&img.complete&&img.naturalWidth){cx.drawImage(img,x,y,w,h);return}
  if(fallback){cx.fillStyle=fallback;cx.fillRect(x,y,w,h)}}
"""

TEMPLATES: dict[str, GameTemplate] = {
    "fishing": GameTemplate(
        "fishing",
        "タイミング釣り",
        "動くマーカーが帯の中にある間に SPACE かクリック。",
        _FISHING,
    ),
    "catch": GameTemplate(
        "catch",
        "落ちものキャッチ",
        "落ちてくるものを受け皿で拾う。← → かマウスで動かす。",
        _CATCH,
    ),
    "adventure": GameTemplate(
        "adventure",
        ADVENTURE_TITLE,
        ADVENTURE_HOW,
        ADVENTURE_SCRIPT,
    ),
}

#: Difficulty is two numbers per template, not a label. Keeping the mapping
#: here means "難しくして" changes the game rather than the wording.
_DIFFICULTY = {
    "fishing": {"easy": (0.008, 0.34), "normal": (0.014, 0.22), "hard": (0.024, 0.12)},
    "catch": {"easy": (34, 0.30), "normal": (22, 0.20), "hard": (13, 0.12)},
    "adventure": ADVENTURE_DIFFICULTY,
}

# Stems, not whole words: 難しい / 難しく / 難しめ all have to land on the
# same setting, and a request that says "難しい" and gets "normal" is the
# quiet kind of wrong - the page still works, so nothing complains.
_HARD = ("難し", "むずかし", "ハード", "hard", "難易度高")
_EASY = ("簡単", "やさし", "かんたん", "easy", "初心者")
_FISHING_WORDS = ("釣り", "つり", "fishing", "魚")
_CATCH_WORDS = ("キャッチ", "catch", "受け", "落ちもの", "避け")
_ADVENTURE_WORDS = ADVENTURE_WORDS

#: Names this generator will not put on an artifact. A request that says
#: 「ゼルダの伝説作って」 routes to the adventure template - the *genre* is
#: buildable - but the name belongs to someone, and a generated page carrying
#: it would read as a claim to be that work. The video that motivated the
#: template made the same choice: an original game by people who loved the
#: original. Matched casefolded, and deliberately short: this is a courtesy
#: guard for the names operators actually type, not a trademark database.
_TRADEMARKS = (
    "ゼルダ",
    "マリオ",
    "ポケモン",
    "ポケットモンスター",
    "ドラクエ",
    "ドラゴンクエスト",
    "ファイナルファンタジー",
    "カービィ",
    "ドラゴンボール",
    "スプラトゥーン",
    "どうぶつの森",
    "モンハン",
    "モンスターハンター",
    "zelda",
    "mario",
    "pokemon",
    "kirby",
    "dragon ball",
    "nintendo",
    "任天堂",
)

_STRIP = re.compile(
    r"(を|の)?\s*(ゲーム|game)?\s*(を)?\s*(作って|作成して|生成して|つくって|作れ|ください|下さい)\s*[。.!！]?\s*$"
)


def choose_template(request: str) -> str:
    """Pick by what the request names, defaulting to the fishing template."""

    lowered = request.lower()
    if any(word.lower() in lowered for word in _ADVENTURE_WORDS):
        return "adventure"
    if any(word in lowered for word in _CATCH_WORDS):
        return "catch"
    if any(word in lowered for word in _FISHING_WORDS):
        return "fishing"
    return "fishing"


#: Genre words an operator actually types, mapped to the template key that
#: would satisfy them. A genre is "supported" when its key is present in
#: :data:`TEMPLATES` - the table names the *promise*, not the inventory, so a
#: template landing later flips the answer without anyone editing this list.
#: Order is the tie-break: "対戦シューティング" is a shooter, not a versus game.
_GENRES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "アドベンチャー",
        "adventure",
        ("アドベンチャー", "adventure", "ゼルダ", "冒険", "ダンジョン", "探索"),
    ),
    (
        "シューティング",
        "shooter",
        ("シューティング", "shooting", "shooter", "stg", "弾幕", "シューター"),
    ),
    ("パズル", "puzzle", ("パズル", "puzzle")),
    ("レース", "racing", ("レース", "レーシング", "racing", "race")),
    ("RPG", "rpg", ("rpg", "ロールプレイング", "ロープレ")),
    (
        "対戦格闘",
        "versus",
        ("格闘", "対戦", "versus", "fighting", "ドラゴンボール", "ビーム"),
    ),
    ("プラットフォーマー", "platformer", ("プラットフォーマー", "platformer", "横スクロール")),
    (
        "シミュレーション",
        "simulation",
        ("シミュレーション", "simulation", "経営ゲーム"),
    ),
    ("ノベル", "novel", ("ノベルゲーム", "ノベル", "visual novel", "サウンドノベル")),
    ("リズム", "rhythm", ("リズムゲーム", "音ゲー", "rhythm")),
    ("キャッチ", "catch", _CATCH_WORDS),
    ("釣り", "fishing", _FISHING_WORDS),
)


@dataclass(frozen=True)
class GenreRequest:
    """What genre the request named, and whether we can honour it.

    ``supported`` is derived from :data:`TEMPLATES` at call time rather than
    stored, so the honest-refusal wording cannot outlive the gap it describes.
    """

    genre: str
    template: str

    @property
    def supported(self) -> bool:
        return self.template in TEMPLATES


def detect_genre(request: str) -> GenreRequest | None:
    """Name the genre the request asked for, or ``None`` if it named none.

    "ゲームを作って" names no genre: there is nothing to be dishonest about,
    so the caller must not add a caveat. Only a request that says a genre out
    loud can be answered with the wrong one.
    """

    lowered = request.lower()
    for genre, key, words in _GENRES:
        if any(word.lower() in lowered for word in words):
            return GenreRequest(genre=genre, template=key)
    return None


def choose_difficulty(request: str) -> str:
    lowered = request.lower()
    if any(word in lowered for word in _HARD):
        return "hard"
    if any(word in lowered for word in _EASY):
        return "easy"
    return "normal"


def _title_from(request: str, fallback: str) -> str:
    """Use the operator's own words when they named the thing.

    Their phrasing is better than ours and it is not a claim about anything,
    so there is nothing to verify - unlike the numbers a deck would carry.
    """

    stripped = _STRIP.sub("", request.strip()).strip("「」\"' 　")
    if 1 <= len(stripped) <= 24:
        return stripped
    return fallback


def _no_external_assets(html: str) -> bool:
    for match in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", html):
        if match.group(1).strip().lower().startswith(("http://", "https://", "//")):
            return False
    return "@import" not in html


def _page(
    title: str, tagline: str, how: str, script: str, evidence: list[str], theme: Theme
) -> str:
    t = theme.tokens
    sources = "".join(f"<li>{escape(line)}</li>" for line in evidence)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<style>
:root{{color-scheme:{t["scheme"]}}}
body{{margin:0;background:{t["bg"]};color:{t["text"]};
 font-family:system-ui,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:32px 20px 48px}}
h1{{font-size:22px;margin:0 0 6px;letter-spacing:.01em}}
p.tag{{margin:0 0 20px;color:{t["subtle"]}}}
canvas{{display:block;width:100%;height:320px;background:{t["surface"]};
 border:1px solid {t["border"]};border-radius:{t["radius"]}}}
.how{{margin:18px 0 0;padding:14px 16px;background:{t["raised"]};
 border-radius:{t["radius_tight"]};font-family:ui-monospace,SFMono-Regular,monospace;
 font-size:13px;color:{t["code"]}}}
footer{{margin-top:28px;border-top:1px solid {t["border"]};padding-top:14px;
 font-size:12px;color:{t["muted"]}}}
footer ul{{margin:6px 0 0;padding-left:18px}}
a{{color:{t["accent"]}}}
</style></head>
<body><main>
<h1>{escape(title)}</h1>
<p class="tag">{escape(tagline)}</p>
<canvas id="stage" width="720" height="320"></canvas>
<p class="how">{escape(how)}</p>
<footer>SIDRA AI が生成。配色と禁止事項の出典:
<ul>{sources}</ul></footer>
</main>
<script>
{script}
</script></body></html>
"""


def generate_game(
    request: str,
    *,
    template: str = "",
    evidence: list[str] | None = None,
    sprites: dict[str, str] | None = None,
) -> GeneratedGame:
    """Build a playable page from the request alone. Never raises on wording.

    ``sprites`` maps a name the templates draw (``target``, ``marker``) to a
    path the page loads it from. Only a project passes it: a standalone page
    must stay one file, so the default is no sprites and the identical
    rectangles this shipped with.
    """

    key = template or choose_template(request)
    if key not in TEMPLATES:
        raise KeyError(f"unknown game template: {key!r}")
    spec = TEMPLATES[key]
    # The palette comes from the same sentence the template and difficulty
    # did. A request that names no theme gets the default, which is the
    # site's own palette - see sidra_ai.creation.themes.
    theme = select_theme(request)
    difficulty = choose_difficulty(request)
    speed, band = _DIFFICULTY[key][difficulty]
    script = with_animation(
        (_SPRITE_LOADER + spec.script)
        .replace("SPRITE_MAP_TOKEN", json.dumps(sprites or {}))
        .replace("SPEED_TOKEN", str(speed))
        .replace("BAND_TOKEN", str(band))
        .replace("SURFACE_TOKEN", theme.tokens["surface"])
        .replace("RAISED_TOKEN", theme.tokens["raised"])
        .replace("CYAN_TOKEN", theme.tokens["accent"])
        .replace("MAGENTA_TOKEN", theme.tokens["alert"])
        # The layout seed: same request, same world. Templates without the
        # token are byte-for-byte unaffected by the replace.
        .replace("SEED_TOKEN", str(zlib.crc32(request.encode("utf-8"))))
    )
    title = _title_from(request, spec.default_title)
    tagline = f"難易度 {difficulty} / テンプレート {key}"
    named = next((mark for mark in _TRADEMARKS if mark.lower() in title.lower()), "")
    if named:
        # The genre is buildable; the name is someone's. Swap the title for
        # the template's own and say so where the operator will read it -
        # silently renaming would look like a bug, not a decision.
        title = spec.default_title
        # The notice itself names no mark: the artifact is distributed, and
        # a disclaimer that prints the trademark still prints the trademark.
        tagline = "依頼にあった作品名は使えないためオリジナル版 / " + tagline
    html = _page(title, tagline, spec.how_to_play, script, list(evidence or [_SOURCE]), theme)
    return GeneratedGame(key, title, tagline, difficulty, html)


def save_game(game: GeneratedGame, data_dir: str | Path, *, now: datetime | None = None) -> Path:
    """Write the artifact locally. Nothing leaves the machine."""

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory = Path(data_dir) / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"game-{game.template}-{stamp}.html"
    path.write_text(game.html, encoding="utf-8")
    return path


# -------------------------------------------------------------- validation


def _script_of(html: str) -> str:
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    return match.group(1) if match else ""


def _javascript_parses(script: str) -> tuple[bool, str]:
    """Parse the script with node when there is one; say which check ran.

    A checker that silently degrades is worse than no checker: "playable"
    would keep reporting 1 on a page whose script never parsed. The reason
    string names the tool so the metric's detail cannot hide the difference.
    """

    try:
        result = subprocess.run(
            ["node", "--check", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        balanced = _brackets_balanced(script)
        return balanced, "no node: brackets only" if balanced else "no node: unbalanced"
    if result.returncode == 0:
        return True, "node --check"
    return False, f"node --check: {result.stderr.strip().splitlines()[:1]}"


def _brackets_balanced(script: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in script:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def validate_game_html(html: str) -> dict:
    """Report every reason the page would not be playable, not just the first."""

    from html.parser import HTMLParser

    failures: list[str] = []

    class _Parse(HTMLParser):
        def error(self, message):  # pragma: no cover - stdlib never calls this
            failures.append(f"html: {message}")

    parser = _Parse(convert_charrefs=True)
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # noqa: BLE001 - a parse failure is a finding
        failures.append(f"html: {type(exc).__name__}: {exc}")

    if "<canvas" not in html:
        failures.append("no <canvas>")
    script = _script_of(html)
    if not script.strip():
        failures.append("no <script>")
    checker = "not run"
    if script.strip():
        parses, checker = _javascript_parses(script)
        if not parses:
            failures.append(f"javascript did not parse ({checker})")
    if not _no_external_assets(html):
        failures.append("references an external asset")

    return {"playable": not failures, "failures": failures, "js_checker": checker}


def report(game: GeneratedGame) -> str:
    return json.dumps(
        {"template": game.template, "title": game.title, "difficulty": game.difficulty},
        ensure_ascii=False,
    )
