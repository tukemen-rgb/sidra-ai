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
from sidra_ai.creation.adapt import preamble_for as adapt_preamble_for
from sidra_ai.creation.animation import with_animation
from sidra_ai.creation.combo import preamble_for as combo_preamble_for
from sidra_ai.creation.graze import preamble_for as graze_preamble_for
from sidra_ai.creation.intent import fold_kana
from sidra_ai.creation.audio import COMBAT_GAIN, MAX_GAIN, SFX_PREAMBLE
from sidra_ai.creation.ghost import preamble_for as ghost_preamble_for
from sidra_ai.creation.juice import JUICE_PREAMBLE
from sidra_ai.creation.music import MUSIC_PREAMBLE
from sidra_ai.creation.remap import preamble_for as remap_preamble_for
from sidra_ai.creation.marble import (
    MARBLE_HOW,
    MARBLE_SCRIPT,
    MARBLE_TITLE,
    MARBLE_WORDS,
)
from sidra_ai.creation.scene import (
    ADVENTURE_PALETTE,
    FISHING_PALETTE,
    MARBLE_PALETTE,
    KAIJU_PALETTE,
    RACING_PALETTE,
    PLATFORMER_PALETTE,
    SHOOTER_PALETTE,
    SCENE_PREAMBLE,
)
from sidra_ai.creation.startscreen import BRIEFINGS, GATE_PREAMBLE
from sidra_ai.creation.puzzle import (
    PUZZLE_DIFFICULTY,
    PUZZLE_HOW,
    PUZZLE_SCRIPT,
    PUZZLE_TITLE,
    PUZZLE_WORDS,
)
from sidra_ai.creation.shooter import (
    SHOOTER_DIFFICULTY,
    SHOOTER_HOW,
    SHOOTER_SCRIPT,
    SHOOTER_TITLE,
    SHOOTER_WORDS,
)
from sidra_ai.creation.kaiju import (
    KAIJU_DIFFICULTY,
    KAIJU_HOW,
    KAIJU_SCRIPT,
    KAIJU_TITLE,
    KAIJU_WORDS,
)
from sidra_ai.creation.racing import (
    RACING_DIFFICULTY,
    RACING_HOW,
    RACING_LAPS,
    RACING_SCRIPT,
    RACING_TITLE,
    RACING_WORDS,
)
from sidra_ai.creation.platformer import (
    PLATFORMER_DIFFICULTY,
    PLATFORMER_HOW,
    PLATFORMER_SCRIPT,
    PLATFORMER_TITLE,
    PLATFORMER_WORDS,
)
from sidra_ai.creation.touchpad import PAD_PREAMBLE
from sidra_ai.creation.daily import DAILY_PREAMBLE
from sidra_ai.creation.round import preamble_for as round_preamble_for
from sidra_ai.creation.parts import PARTS_PREAMBLE
from sidra_ai.creation.share import preamble_for as share_preamble_for
from sidra_ai.creation.skins import preamble_for as skin_preamble_for
from sidra_ai.creation.tuning import TUNE_PREAMBLE, panel_schema
from sidra_ai.creation.duel import (
    DUEL_DIFFICULTY,
    DUEL_HOW,
    DUEL_SCRIPT,
    DUEL_TITLE,
    DUEL_WORDS,
)

#: Re-exported from :mod:`sidra_ai.creation.themes`, which is where the site's
#: DESIGN.md §2 palette now lives: the default theme has to *be* these tokens
#: rather than a second copy of them, and a module that owns both cannot be
#: imported by the one that owns neither. Every existing
#: ``from ...games import GAMEYARD_TOKENS`` keeps working.
from sidra_ai.creation.themes import GAMEYARD_TOKENS, THEMES, Theme, select_theme

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
const SPEED=SPEED_TOKEN,BAND=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
/* Where the fish are today. It used to be the middle, always, for
   everybody - which meant this page had no board a seed could decide and
   so could not honestly join 今日の挑戦 (C-1118 found it claiming to).
   Kept off the edges so the band always fits on the line. */
const SPOT=0.25+rand()*0.5;
let pos=0,dir=1,score=0,casts=0,flash=0,msg='SPACE / クリックで合わせる';
const zone=()=>[SPOT-BAND/2,SPOT+BAND/2];
/* A timing game has no course, so the round clock is the journey: the
   sixty seconds split into three skies, and the brightest one is the
   last (§7 観察 5-6 over §8's round). ROUND_MS counts played time only,
   so the title screen spends none of the day. */
setPal(FISHING_PAL_TOKEN);
function step(){setScene(Math.min(2,ROUND_MS/(ROUND_LIMIT_MS/3)|0));
  pos+=dir*SPEED;if(pos>1){pos=1;dir=-1}if(pos<0){pos=0;dir=1}draw();
  requestAnimationFrame(step)}
function draw(){const w=cv.width,h=cv.height,now=performance.now();
  cx.fillStyle=scenePaint('SURFACE_TOKEN');
  cx.fillRect(0,0,w,h);const [a,b]=zone();
  cx.fillStyle=scenePaint('RAISED_TOKEN');cx.fillRect(40,h/2-26,w-80,52);
  cx.fillStyle='CYAN_TOKEN';cx.globalAlpha=0.28;
  cx.fillRect(40+(w-80)*a,h/2-26,(w-80)*(b-a),52);cx.globalAlpha=1;
  /* decorative: a four-frame bob on the target sprite. FRAME pins it to 0
     under reduced motion, so it sits still while the game keeps running. */
  const bob=[0,-3,0,3][FRAME(4,6,now)];
  /* the catch flash eases out; ease() is the identity when reduced */
  if(flash>0){cx.globalAlpha=0.35*ease(flash);cx.fillStyle='CYAN_TOKEN';
    cx.fillRect(0,0,w,h);cx.globalAlpha=1;flash-=0.04}
  sprite('marker',40+(w-80)*pos-8,h/2-34,16,68,'MAGENTA_TOKEN');
  /* The fish itself: body, tail, eye (C-1206). Every other empty-fallback
     sprite slot sits over a procedural body; this one had none, so the
     page computed a bob for a target it never drew. Painted before the
     sprite call so a real asset in the 'target' slot covers it. */
  const fx=40+(w-80)*SPOT,fy=h/2+bob;
  cx.fillStyle='CYAN_TOKEN';cx.beginPath();
  cx.ellipse(fx+3,fy,13,8,0,0,6.284);cx.fill();
  cx.beginPath();cx.moveTo(fx-8,fy);cx.lineTo(fx-16,fy-7);cx.lineTo(fx-16,fy+7);
  cx.closePath();cx.fill();
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(fx+9,fy-3,3,3);
  sprite('target',40+(w-80)*SPOT-16,h/2-16+bob,32,32,'');
  cx.fillStyle='#dfe7f5';cx.font='16px ui-monospace,monospace';
  cx.fillText(msg,40,h-28);cx.fillText('釣果 '+score+' / '+casts,40,34)}
function fishFacts(){return {pos:pos,spot:SPOT,band:BAND,score:score,
  casts:casts,scene:SCENE,ms:ROUND_MS}}
function cast(){casts++;const [a,b]=zone();
  if(pos>=a&&pos<=b){score++;flash=1;msg='かかった。';sfx('catch');
    shake(4);hitstop(2);burst(cv.width/2,cv.height/2,14,'ACCENT_JUICE')}
  else{msg='逃げられた。';sfx('clash');shake(1.5)}}
addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault();cast()}});
cv.addEventListener('pointerdown',cast);
step();
"""

_CATCH = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const FALL=SPEED_TOKEN,WIDE=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
let px=0.5,shown=0.5,items=[],score=0,caught=0,missed=0,t=0,firstDrop=true;
addEventListener('keydown',e=>{if(e.code==='ArrowLeft'){px=Math.max(0,px-0.06)}
  if(e.code==='ArrowRight'){px=Math.min(1,px+0.06)}});
cv.addEventListener('pointermove',e=>{const r=cv.getBoundingClientRect();
  px=Math.min(1,Math.max(0,(e.clientX-r.left)/r.width))});
function step(){t++;if(t%FALL===0){
  /* The first one falls straight into the basket, wherever it is (§8 事実
     5). Everything after it is luck, as it should be - but the opening
     has to hand something over before it asks for anything. */
  /* Seeded, so today's board is the same board for everyone who plays it
     (C-1119). Math.random gave every device a different run and left this
     page unable to join 今日の挑戦 honestly. */
  items.push({x:firstDrop?shown:rand(),y:0});firstDrop=false}
  const w=cv.width,h=cv.height;
  items.forEach(i=>{i.y+=0.012});
  items=items.filter(i=>{if(i.y<0.92)return true;
    if(Math.abs(i.x-shown)<WIDE/2){
      /* The run is worth what it is worth at the moment it pays out
         (C-1405). Asked once, so the points added and the number drawn
         cannot disagree. */
      caught++;score+=comboHit();sfx('catch');
      shake(2);burst(i.x*cv.width,cv.height-30,10,'ACCENT_JUICE')}
    else{comboMiss();missed++;sfx('clash');shake(5);hitstop(2)}return false});
  cx.fillStyle='SURFACE_TOKEN';cx.fillRect(0,0,w,h);
  /* the basket eases toward the pointer instead of snapping to it */
  shown+=(px-shown)*(REDUCED?1:0.25);
  /* decorative: a four-frame pulse, frozen when reduced */
  const pulse=[0,1,2,1][FRAME(4,8,performance.now())];
  items.forEach(i=>{sprite('target',i.x*w-10,i.y*h,20,20,'CYAN_TOKEN')});
  sprite('marker',(shown-WIDE/2)*w,h-30-pulse,WIDE*w,20+pulse,'MAGENTA_TOKEN');
  cx.fillStyle='#dfe7f5';cx.font='16px ui-monospace,monospace';
  /* The multiplier is on screen at x1 as much as at x4, and the raw
     count stays beside the points so 「得点」 cannot be mistaken for it. */
  cx.fillText('得点 '+score+' '+comboLabel()+' / 受け '+caught+' / こぼし '+missed,40,34);
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
#: Keyboard play must not scroll the page (C-1215). The browser's default
#: for arrows and Space is scrolling, so walking south in the adventure
#: pushed the board off screen (208px in six presses - and every template
#: shares this shell). Guarded once, on the native listener before the
#: remap wrapper exists, and only when focus is not on a form control:
#: the tuning panel's sliders and inputs keep their arrow keys.
_SCROLL_GUARD = """
addEventListener('keydown',function(e){
  const t=(e.target&&e.target.tagName)||'';
  if(/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(t))return;
  if([' ','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].indexOf(e.key)>=0)e.preventDefault();
});
"""

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
    "duel": GameTemplate(
        "duel",
        DUEL_TITLE,
        DUEL_HOW,
        DUEL_SCRIPT,
    ),
    "shooter": GameTemplate(
        "shooter",
        SHOOTER_TITLE,
        SHOOTER_HOW,
        SHOOTER_SCRIPT,
    ),
    "puzzle": GameTemplate(
        "puzzle",
        PUZZLE_TITLE,
        PUZZLE_HOW,
        PUZZLE_SCRIPT,
    ),
    "kaiju": GameTemplate(
        "kaiju",
        KAIJU_TITLE,
        KAIJU_HOW,
        KAIJU_SCRIPT,
    ),
    "racing": GameTemplate(
        "racing",
        RACING_TITLE,
        RACING_HOW,
        RACING_SCRIPT,
    ),
    "marble": GameTemplate(
        "marble",
        MARBLE_TITLE,
        MARBLE_HOW,
        MARBLE_SCRIPT,
    ),
    "platformer": GameTemplate(
        "platformer",
        PLATFORMER_TITLE,
        PLATFORMER_HOW,
        PLATFORMER_SCRIPT,
    ),
}

#: Difficulty is two numbers per template, not a label. Keeping the mapping
#: here means "難しくして" changes the game rather than the wording.
_DIFFICULTY = {
    "marble": {"easy": (3.4, 34), "normal": (4.6, 26), "hard": (6.2, 19)},
    "fishing": {"easy": (0.008, 0.34), "normal": (0.014, 0.22), "hard": (0.024, 0.12)},
    "catch": {"easy": (34, 0.30), "normal": (22, 0.20), "hard": (13, 0.12)},
    "adventure": ADVENTURE_DIFFICULTY,
    "duel": DUEL_DIFFICULTY,
    "shooter": SHOOTER_DIFFICULTY,
    "puzzle": PUZZLE_DIFFICULTY,
    "kaiju": KAIJU_DIFFICULTY,
    "racing": RACING_DIFFICULTY,
    "platformer": PLATFORMER_DIFFICULTY,
}

# Stems, not whole words: 難しい / 難しく / 難しめ all have to land on the
# same setting, and a request that says "難しい" and gets "normal" is the
# quiet kind of wrong - the page still works, so nothing complains.
_HARD = ("難し", "むずかし", "ハード", "hard", "難易度高")
_EASY = ("簡単", "やさし", "かんたん", "easy", "初心者")
_FISHING_WORDS = ("釣り", "つり", "fishing", "魚")
_CATCH_WORDS = ("キャッチ", "catch", "受け", "落ちもの", "避け")
_ADVENTURE_WORDS = ADVENTURE_WORDS
_DUEL_WORDS = DUEL_WORDS
_SHOOTER_WORDS = SHOOTER_WORDS
_PUZZLE_WORDS = PUZZLE_WORDS
_KAIJU_WORDS = KAIJU_WORDS
_RACING_WORDS = RACING_WORDS
_PLATFORMER_WORDS = PLATFORMER_WORDS

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
    # Added with the kaiju template: the *genre* is now buildable, so the
    # request routes instead of apologising - which makes the name guard the
    # only thing standing between a franchise request and a page carrying the
    # franchise's name.
    "ゴジラ",
    "ガメラ",
    "ウルトラマン",
    "zelda",
    "mario",
    "pokemon",
    "kirby",
    "dragon ball",
    "godzilla",
    "gamera",
    "ultraman",
    "nintendo",
    "任天堂",
)

_STRIP = re.compile(
    r"(を|の)?\s*(ゲーム|game)?\s*(を)?\s*(作って|作成して|生成して|つくって|作れ|ください|下さい)\s*[。.!！]?\s*$"
)


def choose_template(request: str) -> str:
    """Pick by what the request names, defaulting to the fishing template."""

    lowered = fold_kana(request.lower())
    # Before the duel: "対戦シューティング" is a shooter, and _GENRES already
    # says so. Routing has to agree with the honesty table or the summary
    # would name a genre the page is not.
    # Before the shooter and the adventure: 「巨大な怪獣を撃つ」 names a boss
    # fight, and a request whose subject is the monster should not land on a
    # template where every enemy is the player's size.
    # Before every genre word: 「3D のシューティング」 names a dimension the
    # other nine cannot draw at all, so the dimension outranks the verb.
    if any(fold_kana(word.lower()) in lowered for word in MARBLE_WORDS):
        return "marble"
    if any(fold_kana(word.lower()) in lowered for word in _KAIJU_WORDS):
        return "kaiju"
    if any(fold_kana(word.lower()) in lowered for word in _PUZZLE_WORDS):
        return "puzzle"
    if any(fold_kana(word.lower()) in lowered for word in _SHOOTER_WORDS):
        return "shooter"
    if any(fold_kana(word.lower()) in lowered for word in _ADVENTURE_WORDS):
        return "adventure"
    # Before the duel and the catch, matching _GENRES: 「レースで対戦」 is a
    # race (対戦 is a duel word), and an obstacle-race request that says
    # 「避けながら走る」 must not fall into the catch template on 避け. The
    # word that names the genre outranks the words describing its verbs.
    if any(fold_kana(word.lower()) in lowered for word in _RACING_WORDS):
        return "racing"
    if any(fold_kana(word.lower()) in lowered for word in _DUEL_WORDS):
        return "duel"
    # After the shooter, the adventure and the duel, agreeing with _GENRES:
    # 「横スクロール」 is a modifier as often as a genre, and
    # 「横スクロールシューティング」 names a shooter, not a platformer.
    if any(fold_kana(word.lower()) in lowered for word in _PLATFORMER_WORDS):
        return "platformer"
    if any(fold_kana(word) in lowered for word in _CATCH_WORDS):
        return "catch"
    if any(fold_kana(word) in lowered for word in _FISHING_WORDS):
        return "fishing"
    return "fishing"


#: Genre words an operator actually types, mapped to the template key that
#: would satisfy them. A genre is "supported" when its key is present in
#: :data:`TEMPLATES` - the table names the *promise*, not the inventory, so a
#: template landing later flips the answer without anyone editing this list.
#: Order is the tie-break: "対戦シューティング" is a shooter, not a versus game.
_GENRES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # First of all: 3D names a dimension none of the other nine can
    # draw, so it outranks every word describing what you do in it.
    ("3D コース", "marble", MARBLE_WORDS),
    # Then: a giant-boss request names the monster, and every other genre
    # word in the sentence ("撃つ", "冒険") is describing what you do to it.
    ("巨大ボス", "kaiju", KAIJU_WORDS),
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
    # The template module owns the vocabulary, as with kaiju and the duel:
    # one list routes and one list answers, so they cannot drift.
    ("レース", "racing", RACING_WORDS),
    ("RPG", "rpg", ("rpg", "ロールプレイング", "ロープレ")),
    # Before 対戦格闘: a franchise-beam request is a duel we *can* build, and
    # first-match order is what keeps it from falling into the fighting-game
    # apology below.
    ("ビーム対戦", "duel", DUEL_WORDS),
    (
        "対戦格闘",
        "fighter",
        ("格闘", "fighting", "格ゲー"),
    ),
    ("プラットフォーマー", "platformer", PLATFORMER_WORDS),
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

    lowered = fold_kana(request.lower())
    for genre, key, words in _GENRES:
        if any(fold_kana(word.lower()) in lowered for word in words):
            return GenreRequest(genre=genre, template=key)
    return None


def choose_difficulty(request: str) -> str:
    lowered = request.lower()
    if any(word in lowered for word in _HARD):
        return "hard"
    if any(word in lowered for word in _EASY):
        return "easy"
    return "normal"


def trademark_in(title: str) -> str:
    """The first trademark a title carries, or an empty string.

    One helper shared by every place that names an artifact - the standalone
    game page and the whole-production scaffold - because the C-1011 leftover
    was exactly this check existing in one of them: the game renamed itself
    while 「ゼルダみたいな冒険ゲームを企画から作って」 kept the mark in every
    document heading and in the directory name.
    """

    return next((mark for mark in _TRADEMARKS if mark.lower() in title.lower()), "")


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
    # The canvas must keep its intrinsic 720:320 ratio at every page width:
    # `width:100%` with a pixel height squashed every game 2x horizontally on
    # a phone while desktop (main max-width 760 - padding = 720) looked
    # perfect, so nobody saw it (C-1204). `height:auto` scales height from
    # the width/height attributes, the same rule art.py always used.
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
canvas{{display:block;width:100%;height:auto;background:{t["surface"]};
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
    difficulty: str = "",
    theme_name: str = "",
    title_override: str = "",
    panel: dict | None = None,
) -> GeneratedGame:
    """Build a playable page from the request alone. Never raises on wording.

    ``sprites`` maps a name the templates draw (``target``, ``marker``) to a
    path the page loads it from. Only a project passes it: a standalone page
    must stay one file, so the default is no sprites and the identical
    rectangles this shipped with.

    ``difficulty`` / ``theme_name`` / ``title_override`` exist for the
    revision path (sidra_ai.creation.revise): a revision edits recorded
    parameters and rebuilds from the *original* request, so everything the
    operator did not mention stays as it was. They deliberately do not
    bypass the guards below - an overridden title still goes through the
    trademark check, and an unknown difficulty or theme falls back to the
    derived one rather than raising, because a bad sidecar file must not
    make an artifact unbuildable.
    """

    key = template or choose_template(request)
    if key not in TEMPLATES:
        raise KeyError(f"unknown game template: {key!r}")
    spec = TEMPLATES[key]
    # The palette comes from the same sentence the template and difficulty
    # did. A request that names no theme gets the default, which is the
    # site's own palette - see sidra_ai.creation.themes.
    theme = THEMES.get(theme_name) or select_theme(request)
    if difficulty not in _DIFFICULTY[key]:
        difficulty = choose_difficulty(request)
    speed, band = _DIFFICULTY[key][difficulty]
    # C-1117: a sentence can turn any panel axis, and what it turns is the
    # value the page opens with. The difficulty preset lands first and an
    # explicit axis on top, so 「難しくして、でも帯は広めに」 does both in
    # the order it was said. Speed is deliberately not among them: the
    # ladder *is* the speed axis, and a second one would let the two
    # disagree about what 「速く」 means.
    schema = panel_schema(
        key,
        _DIFFICULTY[key],
        difficulty=difficulty,
        accent=theme.tokens["accent"],
        overrides=panel,
    )
    fields = {f["key"]: f for f in schema["fields"]}
    band = fields["band"]["default"]
    accent = fields["accent"]["default"]
    script = with_animation(
        # Sound before sprites before the game: sfx() has to exist by the
        # time any input handler in the template body can fire. The pad and
        # the juice go with them - both wrap requestAnimationFrame, so they
        # have to be in place before the template's loop takes its first
        # frame. Juice wraps first so the pad ends up drawn on top of the
        # particles rather than under them.
        (
            # Before even the remap wrapper: the scroll guard rides the
            # native addEventListener, so the page never scrolls under the
            # game whatever later wrappers do to key events (C-1215).
            _SCROLL_GUARD
            # First of everything else: the key re-assignment (§4, C-1305)
            # wraps addEventListener, so it must exist before any preamble
            # or template registers a handler - otherwise a remapped key
            # would reach some listeners in the old spelling.
            + remap_preamble_for(key, spec.script)
            # The skins before the panel: TUNE_ACCENT is resolved through
            # skinAccent, so the colour a template paints with is the one
            # the player earned unless they picked one by hand (C-1109).
            + skin_preamble_for(key)
            # Then the panel: every preamble after it, and every template,
            # paints with TUNE_ACCENT and reads its numbers through tuneNum.
            + TUNE_PREAMBLE
            # After the panel (it reads the switch) and before anything
            # that uses SEED_TOKEN, which is every template body.
            + DAILY_PREAMBLE
            + GATE_PREAMBLE
            + SFX_PREAMBLE
            # Right after the effects: the music shares their AC, mute and
            # combat step, and reads SEED through a typeof guard so the
            # seedless templates still get a (fixed) tune (C-1304).
            + MUSIC_PREAMBLE
            + JUICE_PREAMBLE
            + SCENE_PREAMBLE
            + PAD_PREAMBLE
            # Last of the loop wrappers, so the "ここまで" banner is drawn
            # over everything else and holding the frame does not stop the
            # pad or the particles.
            + round_preamble_for(key)
            # After the round: the line it writes is about a round that is
            # over, and it reads the clock's own verdict to know (C-1110).
            + share_preamble_for(key)
            # The past self (C-1401): reads the panel switch, banked by the
            # round clock, drawn by whichever template has a course.
            + ghost_preamble_for(key)
            # Three losses in a row buy one step (C-1402). After the panel,
            # because a hand-set speed always wins.
            + adapt_preamble_for(key, tuple(pair[0] for pair in _DIFFICULTY[key].values()))
            # Consecutive successes pay more (C-1405). After the juice kit,
            # whose shake and burst it celebrates a rise with, and before
            # the template body, which is the only thing that calls it.
            + combo_preamble_for(key)
            # A danger the player may decline (C-1406). Beside the combo
            # for the same reason: it needs the juice kit above it and is
            # called only by the template body below.
            + graze_preamble_for(key)
            # The shared mechanics, such as they are (C-1114). Needs
            # nothing but addEventListener, and is read by two templates.
            + PARTS_PREAMBLE
            + _SPRITE_LOADER
            + spec.script
        )
        # The combat loudness step (§6 観察 4). Substituted rather than
        # written into the preamble so the two numbers live in Python, where
        # the tests can read them.
        .replace("COMBAT_GAIN_TOKEN", str(COMBAT_GAIN))
        .replace("MAX_GAIN_TOKEN", str(MAX_GAIN))
        .replace("SPRITE_MAP_TOKEN", json.dumps(sprites or {}))
        # The two shared axes come through the panel, so a slider in the
        # artifact moves the same number the generator chose. The clamp
        # lives in tuneNum: an absent or out-of-range stored value is the
        # generator's own number, which is why this is a substitution and
        # not a rewrite of nine templates.
        .replace("TUNE_SPEC_TOKEN", json.dumps(schema, ensure_ascii=False))
        # Which template's briefing has been read, per template.
        .replace("GATE_NAME_TOKEN", json.dumps(key))
        # Read once, at load: nothing may shift under a player mid-round.
        .replace("SPEED_TOKEN", f"adaptSpeed(tuneNum('speed',{speed}))")
        # C-1404 (b): difficulty scales scope, not only speed - easy runs
        # fewer laps so the gentlest rung can actually beat the sixty-second
        # clock while every rung keeps a losing path against the clock for
        # weak driving at gentler panel speeds. Only racing carries the
        # token; every other template is byte-for-byte unaffected.
        .replace("LAPS_TOKEN", str(RACING_LAPS.get(difficulty, 3)))
        # C-1404 (b): difficulty scales scope, not only speed - easy runs
        # fewer laps so the gentlest rung can actually beat the sixty-second
        # clock while every rung keeps a losing path against the clock for
        # weak driving at gentler panel speeds. Only racing carries the
        # token; every other template is byte-for-byte unaffected.

        # Read off the schema rather than the ladder, so the panel and the
        # game body cannot disagree about what this page's band is.
        .replace("BAND_TOKEN", f"tuneNum('band',{band})")
        # Quoted first: the accent every template paints with becomes one
        # identifier, so a stored colour repaints all of its uses. Any
        # unquoted CYAN_TOKEN (there are none today) still gets the hex.
        .replace("'CYAN_TOKEN'", "TUNE_ACCENT")
        .replace("SURFACE_TOKEN", theme.tokens["surface"])
        .replace("RAISED_TOKEN", theme.tokens["raised"])
        .replace("CYAN_TOKEN", accent)
        .replace("MAGENTA_TOKEN", theme.tokens["alert"])
        .replace("ACCENT_JUICE", theme.tokens["accent"])
        .replace("ALERT_JUICE", theme.tokens["alert"])
        .replace("BORDER_TOKEN", theme.tokens["border"])
        .replace("BG_TOKEN", theme.tokens["bg"])
        .replace("ADV_PAL_TOKEN", json.dumps([list(p) for p in ADVENTURE_PALETTE]))
        .replace("KAIJU_PAL_TOKEN", json.dumps([list(p) for p in KAIJU_PALETTE]))
        .replace("RACING_PAL_TOKEN", json.dumps([list(p) for p in RACING_PALETTE]))
        .replace("PLAT_PAL_TOKEN", json.dumps([list(p) for p in PLATFORMER_PALETTE]))
        .replace("SHOOTER_PAL_TOKEN", json.dumps([list(p) for p in SHOOTER_PALETTE]))
        .replace("MARBLE_PAL_TOKEN", json.dumps([list(p) for p in MARBLE_PALETTE]))
        .replace("FISHING_PAL_TOKEN", json.dumps([list(p) for p in FISHING_PALETTE]))
        # Before SEED_TOKEN would matter and free of it as a substring: the
        # music's own seed, request-derived, so the same words are the same
        # song in every template - the seedless ones included (C-1304).
        .replace("MUSIC_SEED_INPUT", str(zlib.crc32(request.encode("utf-8"))))
        # The layout seed: same request, same world. Templates without the
        # token are byte-for-byte unaffected by the replace.
        .replace("SEED_TOKEN", f"seedNow({zlib.crc32(request.encode('utf-8'))})")
        # The title screen prints the same words the page prints, so a
        # template whose instructions change cannot leave a stale copy
        # of them on the screen nobody can get past without reading.
        .replace("TITLE_TOKEN", json.dumps(spec.default_title, ensure_ascii=False))
        .replace("HOWTO_TOKEN", json.dumps(spec.how_to_play, ensure_ascii=False))
        # The briefing the title screen prints: objective, controls, threat.
        # A template with no entry gets an empty list and the screen falls
        # back to the instruction line, so a missing briefing costs the
        # framing rather than the start screen.
        .replace(
            "BRIEF_TOKEN",
            json.dumps(list(BRIEFINGS.get(key, ())), ensure_ascii=False),
        )
    )
    title = title_override or _title_from(request, spec.default_title)
    tagline = f"難易度 {difficulty} / テンプレート {key}"
    named = trademark_in(title)
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
    # Second-resolution stamps collide when a revision follows its original
    # inside one second - and silently overwriting the original would make
    # "the old version is still there" a lie. A serial suffix keeps every
    # save a new file.
    serial = 1
    while path.exists():
        serial += 1
        path = directory / f"game-{game.template}-{stamp}-{serial}.html"
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
