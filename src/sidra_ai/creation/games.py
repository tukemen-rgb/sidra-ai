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
from sidra_ai.creation.attract import (
    pilot_call as attract_pilot_call,
    reset_call as attract_reset_call,
    slice_frames as attract_slice_frames,
    wired as attract_wired,
)
from sidra_ai.creation.combo import preamble_for as combo_preamble_for
from sidra_ai.creation.graze import preamble_for as graze_preamble_for
from sidra_ai.creation.recap import preamble_for as recap_preamble_for
from sidra_ai.creation.intent import fold_kana
from sidra_ai.creation.vocabulary import (
    ARTIFACT_NOUNS,
    CATCH_WORDS,
    FISHING_WORDS,
    GENRES,
    labels_for,
)
from sidra_ai.creation.audio import COMBAT_GAIN, MAX_GAIN, SFX_PREAMBLE
from sidra_ai.creation.ghost import preamble_for as ghost_preamble_for
from sidra_ai.creation import probekeys
from sidra_ai.creation.juice import JUICE_PREAMBLE
from sidra_ai.creation.music import MUSIC_PREAMBLE
from sidra_ai.creation.focus import FOCUS_PREAMBLE
from sidra_ai.creation.remap import preamble_for as remap_preamble_for
from sidra_ai.creation.marble import (
    GATE_BASE as MARBLE_GATE_BASE,
    MARBLE_HOW,
    MARBLE_SCRIPT,
    MARBLE_TITLE,
    MARBLE_WORDS,
)
from sidra_ai.creation.scene import (
    ADVENTURE_PALETTE,
    CATCH_PALETTE,
    DUEL_PALETTE,
    FISHING_PALETTE,
    MARBLE_PALETTE,
    KAIJU_PALETTE,
    RACING_PALETTE,
    PLATFORMER_PALETTE,
    PUZZLE_PALETTE,
    SHOOTER_PALETTE,
    SCENE_PREAMBLE,
)
from sidra_ai.creation.startscreen import BRIEFINGS, GATE_PREAMBLE
from sidra_ai.creation.rotate import (
    ROTATE_ID,
    ROTATE_TEXT,
    preamble as rotate_preamble,
)
from sidra_ai.creation.fullscreen import (
    BUTTON_ID as FULL_BUTTON_ID,
    LABEL_ENTER as FULL_LABEL,
    WRAP_ID as FULL_WRAP_ID,
    preamble as fullscreen_preamble,
)
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
from sidra_ai.creation.touchpad import PAD_PREAMBLE, pad_active_declaration
from sidra_ai.creation.daily import preamble_for as daily_preamble
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
    #: What the request itself asked this to be called, before the
    #: trademark guard had a say (C-1125). The guard swaps the title for
    #: the template's own, which used to erase the evidence that the
    #: operator had named a subject at all - and with it the honest note
    #: saying the subject is not in the page. Empty when the request named
    #: nothing and the default was used.
    asked_title: str = ""
    #: Whether the guard did the swapping.
    renamed: bool = False

    def with_copy(self, *, title: str = "", tagline: str = "") -> "GeneratedGame":
        """Overlay model-written wording on a page that already works.

        Empty strings are ignored, so a model that returns nothing leaves the
        deterministic copy standing rather than blanking the page.
        """

        new_title = title.strip() or self.title
        new_tagline = tagline.strip() or self.tagline
        if (new_title, new_tagline) == (self.title, self.tagline):
            return self
        # Replaced through the elements that hold them, never as loose text
        # over the whole page (C-1431). Measured on a fishing page, where
        # the title 「釣り」 occurs five times: two of them are the display
        # copy, and the other three are a browser-tab title, a GTITLE
        # constant that merely *contains* it (「タイミング釣り」) and the
        # share spec's genre name, which is 「釣り」 for a reason that has
        # nothing to do with the title. A loose replace rewrote all five,
        # turning GTITLE into 「タイミング朝凪の一本」 and relabelling the
        # genre with the model's title.
        #
        # Since C-1259 the subtitle names the genre (「ジャンル 釣り」) and a
        # 「釣りゲーム」 request titles the page 「釣り」, so the two fields can
        # share a word - and a bare substitution lets whichever runs first
        # rewrite the other. C-1259 fixed that by ordering the two, tagline
        # before title, which closes one direction only: a model-written
        # *new* tagline containing the *old* title is still cut into by the
        # title pass, and the page ships the mangled line (measured:
        # title 「朝凪の一本」 with tagline 「釣りの朝に。」 rendered
        # 「朝凪の一本の朝に。」). Anchoring removes the crossing itself
        # rather than one of its two directions, so no ordering is load
        # bearing and neither field can reach into the other's element.
        # Each of the three places the copy is *displayed*, replaced through
        # the element that holds it - never as loose text over the page.
        was_title, was_tag = escape(self.title), escape(self.tagline)
        now_title, now_tag = escape(new_title), escape(new_tagline)
        html = self.html
        for before, after in (
            (f"<title>{was_title}</title>", f"<title>{now_title}</title>"),
            (f"<h1>{was_title}</h1>", f"<h1>{now_title}</h1>"),
            (f'<p class="tag">{was_tag}</p>', f'<p class="tag">{now_tag}</p>'),
        ):
            html = html.replace(before, after)
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
let pos=0,dir=1,score=0,hits=0,crits=0,casts=0,flash=0,
  msg='SPACE / クリックで合わせる';
/* The optional danger (§13 事実 1, C-1331): the middle 35% of the band is
   the 会心 zone - waiting for it risks the marker leaving the band, and
   a cautious edge press still pays its 1. Points and fish are counted
   apart (C-1405's precedent), so the number drawn and the number banked
   can never disagree. */
const CRIT=0.35;
/* What a cast is worth, before and outside the run (C-1426). The
   multiplier rides FISH_BASE only; the perfect throw's extra is added
   after it, so a 会心 on a x3 run pays 3+1 rather than 6 - the same
   sum C-1420 settled on for the marble's hot gates. */
const FISH_BASE=1,FISH_CRIT=1;
const zone=()=>[SPOT-BAND/2,SPOT+BAND/2];
/* A timing game has no course, so the round clock is the journey: the
   sixty seconds split into three skies, and the brightest one is the
   last (§7 観察 5-6 over §8's round). ROUND_MS counts played time only,
   so the title screen spends none of the day. */
setPal(FISHING_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1329): draw() paints through these
   constants, so hudFacts() reports what the frame shows. The plate is
   the untinted theme surface at 0.7 over the sky: the brightest final
   act was sinking the themed ink to ~3:1. */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
/* The far layer (§7 観察 7, C-1379): the OTHER all-sky template. The
   catch got its three still clouds in C-1365; the pond's sky stayed a
   single flat fill with the band and marker sitting straight on it.
   Same recipe: fixed positions (no rand() - the seed's spot must not
   move), no motion (nothing for reduced to freeze), the theme's border
   paint faded by FAR_A, drawn under the band so the fish swims in
   front of its own horizon. draw() paints through FAR_A and
   depthFacts() reports the paints - the shared-constant contract. */
const FAR_A=0.45;
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('SURFACE_TOKEN'),solid:scenePaint('BORDER_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
let CAST_ARMED=true;
function step(rt){
  /* The world advances on real time, not on this display's refresh
     rate (§26, C-1608 — the gate C-1607 built and racing proved).
     Drawing is NOT gated: a 120Hz screen still gets 120 pictures a
     second, the world just stops happening twice as fast. */
  if(!TICK(rt)){draw();return requestAnimationFrame(step)}
  worldStep();
  setScene(Math.min(2,ROUND_MS/(ROUND_LIMIT_MS/3)|0));
  pos+=dir*SPEED;if(pos>1){pos=1;dir=-1}if(pos<0){pos=0;dir=1}
  /* The sweep moved, so the next press is a real decision again (C-1500).
     Hitstop skips this whole function, which is exactly what keeps a
     mashed press from scoring twice against one marker position. */
  CAST_ARMED=true;
  draw();
  requestAnimationFrame(step)}
function draw(){const w=cv.width,h=cv.height,now=performance.now();
  cx.fillStyle=scenePaint('SURFACE_TOKEN');
  cx.fillRect(0,0,w,h);
  /* Clouds first, so the band and the fish sit in front (§7, C-1379). */
  cx.fillStyle=scenePaint('BORDER_TOKEN');cx.globalAlpha=FAR_A;
  [[0.18,0.14,76],[0.5,0.09,58],[0.84,0.2,66]].forEach(c=>{
    cx.beginPath();cx.ellipse(c[0]*w,c[1]*h,c[2],c[2]*0.34,0,0,6.284);cx.fill()});
  cx.globalAlpha=1;
  const [a,b]=zone();
  cx.fillStyle=scenePaint('RAISED_TOKEN');cx.fillRect(40,h/2-26,w-80,52);
  cx.fillStyle='CYAN_TOKEN';cx.globalAlpha=0.28;
  cx.fillRect(40+(w-80)*a,h/2-26,(w-80)*(b-a),52);
  /* The multiplier is shown, not hidden (§13 house rule): the 会心 zone
     is the same hue, deeper - a visible reason to wait one more beat. */
  cx.globalAlpha=0.5;
  cx.fillRect(40+(w-80)*(SPOT-(BAND/2)*CRIT),h/2-26,(w-80)*BAND*CRIT,52);
  cx.globalAlpha=1;
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
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(32,14,400,26);cx.fillRect(32,h-44,430,26);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='16px ui-monospace,monospace';
  cx.fillText(msg,40,h-28);
  cx.fillText('得点 '+score+' / 釣果 '+hits+'/'+casts+' / 会心 '+crits
    +' / '+comboLabel(),40,34)}
function fishFacts(){return {pos:pos,spot:SPOT,band:BAND,score:score,
  hits:hits,crits:crits,crit:CRIT,
  casts:casts,scene:SCENE,ms:ROUND_MS}}
function cast(){
  /* One throw per drawn frame (C-1500). Hitstop skips the tick but not
     the key handlers, so during the stop the marker was still parked in
     the zone it just scored in - every further press landed another hit,
     which re-armed the stop before the tick could ever run. Mashing
     therefore froze the round clock for as long as the finger lasted
     (measured: 183ms of round time across 100 wall seconds) while the
     score climbed without bound. Guarding on HITSTOP alone is not
     enough: the press that lands on the exact frame the stop expires
     re-freezes a world that still has not moved. So a cast arms only
     when the sweep has actually advanced - CAST_ARMED is set by step()
     and spent here. The swallowed press is not a miss either: the run
     only breaks on a cast (C-1426), and no cast happened. */
  if(!CAST_ARMED)return;
  CAST_ARMED=false;
  casts++;const [a,b]=zone();
  /* Where the marker stands is where the sound lands (§2 増築, C-1396):
     the sweep is the whole game, so its x is the event's x. */
  const mx=(40+(cv.width-80)*pos)/cv.width;
  if(pos>=a&&pos<=b){hits++;
    /* Asked once, so the number paid and the number shown cannot
       disagree: comboHit() returns the multiplier this cast earned. */
    const pay=comboHit()*FISH_BASE;
    /* The perfect throw pays double and lands heavier (§1): the juice
       scales with the risk that was taken, not just with success. */
    if(Math.abs(pos-SPOT)<=(BAND/2)*CRIT){crits++;
      score+=scorePop(cv.width/2,cv.height/2,pay+FISH_CRIT);
      if(flashGate())flash=1;msg='ど真ん中。会心。';sfx('gem',1,mx);
      shake(6);hitstop(3);burst(cv.width/2,cv.height/2,22,'ACCENT_JUICE')}
    else{score+=scorePop(cv.width/2,cv.height/2,pay);
      if(flashGate())flash=1;msg='かかった。';sfx('catch',1,mx);
      shake(4);hitstop(2);burst(cv.width/2,cv.height/2,14,'ACCENT_JUICE')}}
  /* Only a cast can break the run (C-1426). The sweep between casts is
     what the game asks a player to wait through, so it costs nothing. */
  else{comboMiss();msg='逃げられた。';sfx('clash',1,mx);shake(1.5)}}
addEventListener('keydown',e=>{if(keyInForm(e))return;
  if(e.code==='Space'){e.preventDefault();cast()}});
cv.addEventListener('pointerdown',cast);
step();
"""

_CATCH = """
const cv=document.getElementById('stage'),cx=cv.getContext('2d');
const FALL=SPEED_TOKEN,WIDE=BAND_TOKEN,SEED=SEED_TOKEN;
let rs=(SEED>>>0)||1;function rand(){rs=(rs*48271)%2147483647;return rs/2147483647}
let px=0.5,shown=0.5,items=[],score=0,caught=0,missed=0,t=0,firstDrop=true;
/* The other clock-bound template gets its three skies too (C-1319, the
   catch half of C-1315): the sixty seconds split into thirds and the
   brightest sky is saved for the last stretch. ROUND_MS is played time,
   so the title screen spends none of the day. */
setPal(CATCH_PAL_TOKEN);
/* HUD contract (§4 WCAG 1.4.3, C-1329): same plate as the fishing HUD -
   the untinted theme surface at 0.7 under the text, because the round's
   brightest sky was sinking the themed ink to ~3:1. */
const HUD_INK='INK_TOKEN',HUD_PLATE='SURFACE_TOKEN',HUD_A=0.7;
function hudFacts(){return {ink:HUD_INK,plate:HUD_PLATE,alpha:HUD_A}}
/* The far layer (§7 観察 7, C-1365): the one template whose whole scene
   is sky had no distance in it - the basket in front, the falling fruit
   in the middle, and a single flat fill behind them. Three still clouds
   in the theme's border paint, faded by FAR_A toward the sky, sit under
   the fruit; fixed positions (no rand(): the seed's board never moves)
   and no motion, so reduced motion has nothing to freeze - the kaiju
   ridge's reasoning. Same contract shape as the other four templates':
   draw() paints through FAR_A and depthFacts() reports the paints. */
const FAR_A=0.45;
function depthFacts(){const keep=SCENE,out=[];
  for(let i=0;i<SPAL.length;i++){SCENE=i;
    out.push({sky:scenePaint('SURFACE_TOKEN'),solid:scenePaint('BORDER_TOKEN'),
      alpha:FAR_A})}
  SCENE=keep;return out}
function catchFacts(){return {shown:shown,px:px,score:score,caught:caught,
  missed:missed,scene:SCENE,ms:ROUND_MS,squash:BSQ,
  items:items.map(i=>({x:i.x,y:i.y}))}}
/* Squash & stretch, the receiving half (§1, C-1341): the basket takes an
   impact every catch and was the only rigid body in the frame. Bottom-
   anchored: the catch squashes it to 0.6 and widens it by the same
   budget, and it eases back to rest. Under reduced motion the silhouette
   never changes - C-1332's line, verbatim. */
let BSQ=1;
/* The face (§1, C-1353): the basket watches what it is about to catch.
   The eyes lean toward the LOWEST item - the next one to arrive - with a
   small deadzone so an item already over the basket reads as "looking
   straight ahead". No items is a straight look too. The blink is one
   FRAME beat, pinned open under reduced motion (C-1348's contract). */
function faceLook(){let best=null;
  items.forEach(i=>{if(!best||i.y>best.y)best=i});
  if(!best)return 0;
  return best.x>shown+0.03?1:best.x<shown-0.03?-1:0}
function faceFacts(){return {look:faceLook(),
  blink:FRAME(40,6,performance.now())===1}}
/* Held movement lives in the loop, not in the event (§12 事実 3, C-1328).
   The on-screen pad synthesises no key repeat - one press is one keydown -
   so a basket that only moved inside the event stood still under a held ◀.
   The first press keeps its 0.06 nudge (tap play is unchanged; the flag
   swallows OS repeats) and step() drifts 0.012/frame while held. */
const KHELD={l:false,r:false};
addEventListener('keydown',e=>{
  if(e.code==='ArrowLeft'){if(!KHELD.l){px=Math.max(0,px-0.06)}KHELD.l=true}
  if(e.code==='ArrowRight'){if(!KHELD.r){px=Math.min(1,px+0.06)}KHELD.r=true}});
addEventListener('keyup',e=>{if(e.code==='ArrowLeft'){KHELD.l=false}
  if(e.code==='ArrowRight'){KHELD.r=false}});
cv.addEventListener('pointermove',e=>{const r=cv.getBoundingClientRect();
  px=Math.min(1,Math.max(0,(e.clientX-r.left)/r.width))});
/* The world advances on real time, not on this display's refresh
   rate (§26, C-1608). This template draws inside step(), so the
   gate wraps the simulation prefix only - the brace closes just
   above setScene() and everything below keeps painting at the
   screen's own rate. */
function step(rt){
  /* Hoisted out of the gate: the drawing below the gate needs it too. */
  const w=cv.width,h=cv.height;
  if(TICK(rt)){
  t++;
  if(KHELD.l){px=Math.max(0,px-0.012)}
  if(KHELD.r){px=Math.min(1,px+0.012)}
  if(t%FALL===0){
  /* The first one falls straight into the basket, wherever it is (§8 事実
     5). Everything after it is luck, as it should be - but the opening
     has to hand something over before it asks for anything. */
  /* Seeded, so today's board is the same board for everyone who plays it
     (C-1119). Math.random gave every device a different run and left this
     page unable to join 今日の挑戦 honestly. */
  items.push({x:firstDrop?shown:rand(),y:0});firstDrop=false}
  items.forEach(i=>{i.y+=0.012});
  items=items.filter(i=>{if(i.y<0.92)return true;
    if(Math.abs(i.x-shown)<WIDE/2){
      /* The run is worth what it is worth at the moment it pays out
         (C-1405). Asked once, so the points added and the number drawn
         cannot disagree. */
      caught++;score+=scorePop(i.x*cv.width,cv.height-30,comboHit());
      /* the fruit's own x, for the ear too (§2 増築, C-1396) */
      sfx('catch',1,i.x);
      if(!REDUCED)BSQ=0.6;
      shake(2);burst(i.x*cv.width,cv.height-30,10,'ACCENT_JUICE')}
    else{comboMiss();missed++;sfx('clash',1,i.x);shake(5);hitstop(2)}return false});
  }
  setScene(Math.min(2,ROUND_MS/(ROUND_LIMIT_MS/3)|0));
  cx.fillStyle=scenePaint('SURFACE_TOKEN');cx.fillRect(0,0,w,h);
  /* Clouds first, so the fruit falls in front of them (§7, C-1365). */
  cx.fillStyle=scenePaint('BORDER_TOKEN');cx.globalAlpha=FAR_A;
  [[0.15,0.18,70],[0.55,0.10,90],[0.82,0.26,54]].forEach(c=>{
    cx.beginPath();cx.ellipse(c[0]*w,c[1]*h,c[2],c[2]*0.34,0,0,6.284);cx.fill()});
  cx.globalAlpha=1;
  /* the basket eases toward the pointer instead of snapping to it */
  shown+=(px-shown)*(REDUCED?1:0.25);
  /* decorative: a four-frame pulse, frozen when reduced */
  const pulse=[0,1,2,1][FRAME(4,8,performance.now())];
  items.forEach(i=>{sprite('target',i.x*w-10,i.y*h,20,20,'CYAN_TOKEN')});
  BSQ+=(1-BSQ)*0.25;if(Math.abs(BSQ-1)<0.01)BSQ=1;
  const bh=(20+pulse)*BSQ,bw=WIDE*w*(2-BSQ);
  sprite('marker',shown*w-bw/2,h-10-bh,bw,bh,'MAGENTA_TOKEN');
  /* Eyes on the rim (§1, C-1353), leaning at the next item to arrive.
     Their height rides BSQ, so the catch squashes the eyes with the body
     (C-1341's bounce, one silhouette). */
  const fc=faceFacts();
  if(!fc.blink){cx.fillStyle='#05070f';const ex=fc.look*3;
    cx.fillRect(shown*w-6+ex,h-10-bh+3,3,4*BSQ);
    cx.fillRect(shown*w+3+ex,h-10-bh+3,3,4*BSQ)}
  cx.globalAlpha=HUD_A;cx.fillStyle=HUD_PLATE;
  cx.fillRect(32,14,420,26);cx.fillRect(32,h-44,330,26);cx.globalAlpha=1;
  cx.fillStyle=HUD_INK;cx.font='16px ui-monospace,monospace';
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
/* One name for "the key belongs to a form control, not to the game"
   (C-1671). The shared guard spared the tuning panel from the start, but
   each template's own handler called preventDefault() with no such test,
   so Space on a focused checkbox was swallowed by the game - including
   the panel's own switches. One predicate, used by all of them. */
function keyInForm(e){const t=(e&&e.target&&e.target.tagName)||'';
  return /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(t)}
addEventListener('keydown',function(e){
  if(keyInForm(e))return;
  if([' ','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].indexOf(e.key)>=0)e.preventDefault();
});
"""


#: Does the scroll guard DECIDE, or is it only spelled correctly?
#: (§12, C-1671.) `evals/keys_dont_scroll.py` checks that three literal
#: substrings appear in the HTML and never starts node; its own docstring
#: says the end-to-end proof "ran in a real browser at fix time". A guard
#: registered on the wrong target, or one that returns early, spells the
#: same and does nothing.
#:
#: Scrolling needs a browser. The decision does not: the page's own
#: keydown listeners are called here with a synthetic event, and what is
#: read back is whether preventDefault() was reached.
SCROLLGUARD_PROBE = """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.document = { getElementById: () => ({
  width: 720, height: 320, style: {}, addEventListener: () => {},
  getBoundingClientRect: () => ({left:0, top:0, width:720, height:320}),
  getContext: () => nothing }), addEventListener: () => {} };
let queued = null;
globalThis.requestAnimationFrame = (fn) => { queued = fn; return 1 };
SCRIPT_PLACEHOLDER
PROBE_KEYS_PLACEHOLDER
/* One press, put to a chosen set of the page's listeners, with a real
   target - the guard reads e.target.tagName to spare form controls - and
   a preventDefault that answers back instead of doing nothing. */
function fire(key, tagName, listeners){
  let prevented = false;
  const e = probeKey(key);
  e.target = { tagName: tagName };
  e.preventDefault = function(){ prevented = true };
  listeners.forEach(fn => { try { fn(e) } catch (err) {} });
  return prevented;
}
/* Every keydown listener the page registered, in order. */
function ask(key, tagName){ return fire(key, tagName, handlers.keydown || []) }
const ARROWS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
/* The guard rides the NATIVE addEventListener, before C-1305's remap
   wrapper replaces it - so it must be the first keydown listener the page
   registered. Asked by calling only the first one (C-1671: the old test
   for this compared string offsets in the HTML, which a tidier spelling
   breaks while the ordering is still right). */
function askFirst(key, tagName){
  return fire(key, tagName, (handlers.keydown || []).slice(0, 1)) }
const firstIsGuard = ARROWS.every(k => askFirst(k, 'CANVAS')) &&
  askFirst(' ', 'CANVAS') && !askFirst('a', 'CANVAS') &&
  !ARROWS.some(k => askFirst(k, 'INPUT'));
const board = {};
ARROWS.concat([' ']).forEach(k => { board[k] = ask(k, 'CANVAS') });
/* A key the game does not steer with: a guard that prevents everything
   would take the browser's own shortcuts with it. */
const innocent = ask('a', 'CANVAS');
/* Focus in the tuning panel: the sliders need their arrows back. */
const inForm = {};
['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].forEach(tag => {
  inForm[tag] = { arrows: ARROWS.filter(k => ask(k, tag)), space: ask(' ', tag) } });
console.log(JSON.stringify({ board: board, innocent: innocent, inForm: inForm,
  firstIsGuard: firstIsGuard,
  listeners: (handlers.keydown || []).length }));
"""


def scrollguard_probe(script: str) -> str:
    """The page's own script, wrapped so the guard's decision can be read."""

    return probekeys.with_probe_keys(
        SCROLLGUARD_PROBE.replace("SCRIPT_PLACEHOLDER", script)
    )


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
# C-1120: the words and the genre table live in vocabulary.py now, so the
# detector and the router read the same list. These aliases keep the local
# spelling the rest of this module already uses.
_FISHING_WORDS = FISHING_WORDS
_CATCH_WORDS = CATCH_WORDS
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


#: Where a request lands when it named nothing this product builds. Named
#: once because the decline path and the fall-through have to be the same
#: page, or 「作れないので代わりに既定の…」 would be describing something else.
_DEFAULT_TEMPLATE = "fishing"


def choose_template(request: str) -> str:
    """Pick by what the request names, defaulting to the fishing template."""

    lowered = fold_kana(request.lower())
    # First, and by construction rather than by two lists agreeing: a
    # request that names a genre this product does not build routes to the
    # default, the way 「テトリス」 always has. C-1121 found the ladder below
    # answering 「対戦格闘ゲームを作って」 with a beam duel, because
    # DUEL_WORDS carries bare 「対戦」 and nothing here knew that the genre
    # had already been declined. Keeping the two tables in step by hand is
    # what let them drift; asking the honesty table is what stops it.
    named = detect_genre(request)
    if named is not None and not named.supported:
        return _DEFAULT_TEMPLATE
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
    if any(fold_kana(word) in lowered for word in _CATCH_WORDS):
        return "catch"
    if any(fold_kana(word) in lowered for word in _FISHING_WORDS):
        return "fishing"
    # After the named genres, before the default: 「横スクロール」 is a modifier
    # as often as a genre (「横スクロールシューティング」 is a shooter, matched
    # far above), and the bare 「ジャンプ」/「跳」 added in C-1220 is a verb that
    # names the platformer only when nothing else was named - 「魚が跳ねる釣り」
    # said 釣り, so it stays fishing, per the same "the genre name outranks the
    # verb" rule the earlier branches follow.
    if any(fold_kana(word.lower()) in lowered for word in _PLATFORMER_WORDS):
        return "platformer"
    return _DEFAULT_TEMPLATE


#: Genre words an operator actually types, mapped to the template key that
#: would satisfy them. A genre is "supported" when its key is present in
#: :data:`TEMPLATES` - the table names the *promise*, not the inventory, so a
#: template landing later flips the answer without anyone editing this list.
#: Order is the tie-break: "対戦シューティング" is a shooter, not a versus game.
_GENRES = GENRES


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


#: Stems already consumed by ``choose_difficulty`` plus their okurigana and the
#: 「向け」 an audience phrasing adds (「初心者向け」). Used to tell a request that
#: named *only* a difficulty from one that named a subject: 「むずかしい」 is the
#: difficulty, not a thing the page fails to draw (C-1235).
_DIFFICULTY_ONLY = re.compile(
    "(?:" + "|".join(re.escape(stem) for stem in _HARD + _EASY) + r")[いくめさそうきなの向け]*",
    re.IGNORECASE,
)


def _is_only_difficulty(text: str) -> bool:
    """True when nothing but a difficulty modifier remains after the genre strip.

    「むずかしい」 and 「簡単な」 and 「初心者向け」 are already read as the
    difficulty, so a title built from them - and the 「その題材は描けない」 caveat
    that follows - says the same word is both understood and not.
    """

    left = _DIFFICULTY_ONLY.sub("", text)
    return left.strip("「」\"' 　・のなをがはでゲームgame") == ""


#: The English shape of ``_STRIP`` (C-1516). Japanese puts the making verb
#: at the end, so one trailing pattern took it off and 「レースゲームを作って」
#: became 「レース」. English puts it at the front, nothing took it off, and
#: `make me a racing game` was the page's own title - request and all.
#:
#: The tail is only removed when the head matched, which keeps this the same
#: rule as the Japanese one rather than a wider one: 「レースゲーム」 with no
#: verb keeps both its words, so `racing game` keeps both of its.
#: C-1528: and the heads that carry no making-verb at all. Measured
#: 2026-09-11: `"let's make a puzzle game"` never entered this branch, so the
#: whole request became the page title and the honesty note quoted
#: 「let's make a」 as a thing the page does not draw - the request's own
#: grammar, read back to the operator as their subject. C-1527 widened the
#: door the same week (「I want a…」「we need a…」 now reach a generator), so
#: the list of heads that get here is no longer the list of making-verbs.
#:
#: A head still has to be a verb. Making the bare article one was tried and
#: the judge refused it: `creation_title_drops_make_verb` went 2 -> 0 and
#: `test_a_request_without_a_making_verb_keeps_its_words` failed on 「a racing
#: game」, which is pinned to keep every word the operator used. That pin is
#: the Japanese rule read in English - 「レースゲーム」 keeps both its words
#: too - and widening it here would have been a wider rule in one language
#: than the other, which is the drift this pattern exists inside.
_STRIP_EN_HEAD = re.compile(
    r"^\s*(?:hey\s+|hi\s+)?(?:please\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:"
    r"(?:let\s*'?s\s+)?(?:make|create|build|generate|design|produce|draw|write)\s+(?:me\s+)?"
    r"|(?:i|we)\s*(?:'?d\s*|\s+would\s+)like\s+"
    r"|(?:i|we)\s+(?:want|need)\s+"
    r")"
    r"(?:a|an|the)\s+",
    re.IGNORECASE,
)
#: C-1526: the noun for the thing being made, off the end. Built from
#: ARTIFACT_NOUNS so 「app」 cannot be an artifact noun for the router and a
#: subject for the title in the same repository, and applied until nothing
#: more comes off - 「create a fishing game please」 has two of these
#: stacked, and one pass left 「fishing game」 for the honesty note to
#: quote as a thing the page does not draw.
_STRIP_EN_TAIL = re.compile(
    r"\s*(?:"
    + "|".join(re.escape(w) for w in ARTIFACT_NOUNS if w.isascii())
    + r"|please|thanks|thank you"
    # C-1528: 「for my kid」 is who the game is for, not what is in it, and
    # 「Make a racing game for my kid」 quoted it as the subject the page fails
    # to draw. Only 「for」 - 「about a dog」 names the subject outright and is
    # lifted by `_STRIP_EN_ABOUT`, so the two prepositions are opposites here
    # and must not share a rule.
    + r"|for\s+(?:[\w'-]+\s*){1,3}"
    + r")\s*[,.!?]*\s*$",
    re.IGNORECASE,
)

#: 「a game about a dog」. The artifact noun is the head and the subject
#: comes after it, so trimming the ends cannot reach it - this is the one
#: shape where the request says outright which half is which.
#: The genre may sit in front of the artifact noun - 「a puzzle game about a
#: dog」 - and then the head noun is not the first word left. Measured while
#: fixing C-1528: widening `_STRIP_EN_HEAD` brought that shape into this
#: branch for the first time and, without the leading run, the note quoted
#: 「about a dog」. Two words at most, and lazily, so the preposition matched
#: is the earliest one rather than a later one inside the subject itself.
_STRIP_EN_ABOUT = re.compile(
    r"^(?:[\w'-]+\s+){0,2}?(?:"
    + "|".join(re.escape(w) for w in ARTIFACT_NOUNS if w.isascii())
    + r")\s+(?:about|of|with|featuring|starring)\s+(?:a|an|the)?\s*",
    re.IGNORECASE,
)


def _title_from(request: str, fallback: str) -> str:
    """Use the operator's own words when they named the thing.

    Their phrasing is better than ours and it is not a claim about anything,
    so there is nothing to verify - unlike the numbers a deck would carry.
    """

    stripped = _STRIP.sub("", request.strip()).strip("「」\"' 　")
    # C-1516: the same removal, for the language that puts the verb first.
    # Without it an English request titled its own page `make me a racing
    # game`, and a longer one ("please make a racing game", 25 characters)
    # ran past the length limit below and fell back to the *Japanese*
    # default title - an English request answered with 「タイミング釣り」.
    without_head = _STRIP_EN_HEAD.sub("", stripped, count=1)
    if without_head != stripped:
        without_head = _STRIP_EN_ABOUT.sub("", without_head, count=1)
        trimmed = without_head
        while True:
            shorter = _STRIP_EN_TAIL.sub("", trimmed, count=1).strip("\"' ")
            if shorter == trimmed:
                break
            trimmed = shorter
        # C-1526: an empty result means they named the artifact and nothing
        # else - 「make a game」, the English 「ゲームを作って」. That request
        # gets the default page with no caveat, and keeping the raw request
        # as the title is what made it get one saying 「make a game」 is not
        # drawn.
        stripped = trimmed or fallback
    # A request that named only a difficulty has no subject: titling the page
    # 「むずかしい」 and then claiming its subject cannot be drawn is one word
    # playing both roles (C-1235). Fall back to the template's own title, the
    # same page the bare 「ゲームを作って」 gets.
    if _is_only_difficulty(stripped):
        return fallback
    if 1 <= len(stripped) <= 24:
        return stripped
    return fallback


def undepicted_subject(request: str, template: str, asked_title: str) -> str:
    """What the operator named that the page does not draw.

    C-1205 said this for requests that named no genre at all: 「猫のゲームを
    作って」 got the default fishing page and the summary called it 「猫」.
    Its test for "they named a subject" was 「the title is not the
    template's default」, which two things break.

    The trademark guard replaces the title with the default, so a request
    for a named work looked exactly like a request that named nothing -
    the note vanished precisely where it was most needed. And matching a
    *genre* was treated as satisfying the request, so 「魚の 3D ゲーム」 got
    a marble course titled 「魚の 3D」 with no fish in it and no caveat: the
    genre was honoured and the subject silently dropped.

    So the subject is whatever the request called the thing once the words
    that named the genre are taken out. Nothing left means nothing was
    promised beyond the genre, and a caveat there would be its own
    dishonesty.

    **The words are taken off the ENDS, never out of the middle (C-1503).**
    The first version cut every occurrence wherever it fell and then removed
    fillers the same way, which quoted the operator saying things they never
    said: 「落ちてくるものをキャッチする」 came back as 「落ちてくるもをする」
    - キャッチ gone from the middle, then the 「の」 inside 「もの」 taken with
    the fillers - and 「忍者のアクション」 came back as 「忍者アクション」.
    Trimming from the ends can only ever yield a run of the operator's own
    characters, so the quote is theirs by construction rather than by luck.

    A genre word still sitting INSIDE what is left means the subject and the
    genre cannot be told apart here, and the honest answer is to say nothing:
    the catch page above did honour 「キャッチ」, so a caveat naming the whole
    phrase would be a second lie in the other direction.

    What survives is then checked rather than trusted, because a substring
    can still be debris. 「怪獣を倒す」 on the kaiju page left 「を倒す」 - a
    real run of the request, and grammar rather than subject. A caveat
    quoting a particle is the dishonesty this note exists to avoid.
    """

    if not asked_title:
        return ""
    left = asked_title.strip("「」\"' 　・")
    genre_words: list[str] = []
    for _label, key, words in GENRES:
        if key != template and key in TEMPLATES:
            continue
        genre_words.extend(words)

    # C-1526: and the noun for the thing being made comes off with them.
    # A genre word is trimmed because the page delivered that genre; an
    # artifact noun is trimmed because it never named a subject. Japanese
    # had no such removal either - 「アプリを作って」 came back as 「「アプリ」
    # は絵として出てきません」, and 「レースのアプリを作って」 the same, so
    # the filing's 「日本語側にはもうある」 was not so.
    trimming = True
    while trimming and left:
        trimming = False
        for word in genre_words + list(ARTIFACT_NOUNS) + list(_SUBJECT_FILLERS):
            if not word:
                continue
            lowered, target = left.lower(), word.lower()
            if lowered.startswith(target):
                left = left[len(word) :]
            elif lowered.endswith(target):
                left = left[: len(left) - len(word)]
            else:
                continue
            left = left.strip("「」\"' 　・")
            trimming = True
            break

    # C-1514: the same trimming, for the particle at the *end*. C-1503 gave
    # the caveat a rule against opening with one, and 「を倒す」 stopped being
    # quoted - but 「3D のコースを転がるゲームを作って」 still left 「コースを」,
    # which is the identical dishonesty read from the other side.
    #
    # Trimmed rather than rejected, because trimming is what the operator
    # meant: 「コースを」 becomes 「コース」, a caveat that names the subject,
    # where rejecting it would say nothing about a page that really did not
    # draw a course. Anchored to the end like everything above, so what
    # survives is still a run of the operator's own characters.
    trimming = True
    while trimming and left:
        trimming = False
        for glue in _SUBJECT_GLUE:
            if len(left) > len(glue) and left.endswith(glue):
                left = left[: len(left) - len(glue)].strip("「」\"' 　・")
                trimming = True
                break

    # A genre word still inside is a subject that cannot be quoted apart
    # from it. Silence beats a caveat about a phrase the page did deliver.
    if any(word and word.lower() in left.lower() for word in genre_words):
        return ""

    # C-1524: a clause is cut down to the thing it is about, not silenced.
    # Silencing was tried first and the suite refused it: 「宝石を拾うゲームを
    # 作って」, 「犬が走る…」, 「宇宙を旅する…」 and 「ドラゴンを育てる…」 are
    # requests whose subject the page really does not draw, and
    # ``test_the_note_still_speaks_where_it_was_built_to`` exists to say that
    # silence "would pass every assertion above and fix nothing".
    #
    # So the head is taken: everything before the first case particle, which
    # is the noun the verb is acting on. 「宝石を拾う」 becomes 「宝石」,
    # 「宝の地図を探す」 becomes 「宝の地図」 (「の」 is not a case particle and
    # does not cut). An empty head - 「を倒す」, once the genre word 怪獣 has
    # been trimmed off the front - falls through to the opening-particle rule
    # below and is still refused, which is what C-1503 decided.
    if _is_whole_clause(left):
        head = min(
            (left.index(p) for p in _CASE_PARTICLES if p in left),
            default=len(left),
        )
        left = left[:head].strip("「」\"' 　・")

    # The cut can expose a new trailing particle (「宝の」), so C-1514's rule
    # runs again over what is left.
    trimming = True
    while trimming and left:
        trimming = False
        for glue in _SUBJECT_GLUE:
            if len(left) > len(glue) and left.endswith(glue):
                left = left[: len(left) - len(glue)].strip("「」\"' 　・")
                trimming = True
                break

    # C-1525: and last, the thing the note never asked - does this page
    # actually draw it? Everything above is about quoting the operator
    # faithfully; none of it looks at what was built. So 「巨大な敵と戦う
    # ゲームを作って」 came back as 「『巨獣迎撃戦』型で作りました。ただし
    # 「敵」は絵として出てきません」, which contradicts itself inside one
    # sentence - the 巨獣 IS the enemy, and kaiju.py draws it. The honesty
    # note was lying, in the direction it exists to prevent.
    if left and template_depicts(template, left):
        return ""

    return left if _is_quotable_subject(left, request) else ""


#: Words for things a page draws that its own screens name differently.
#: C-1525: the copy below is the source of truth and answers most of it -
#: marble's briefing says 「コース」, shooter's 操作説明 says 「敵の波」,
#: adventure's says 「宝箱」 - but two pages answer in a synonym, and a
#: caveat is no less false for being about a word the copy happens not to
#: use. Each entry names the drawn object it stands for. Kept short on
#: purpose: a long list here would be a second vocabulary drifting away
#: from the first, which is the failure C-1120 fixed one level up.
_ALSO_DEPICTED: dict[str, tuple[str, ...]] = {
    # The briefing calls it 巨獣 and the page draws exactly one thing to
    # fight, with legs and a head. That is the enemy, the boss and the
    # monster the operator meant.
    "kaiju": ("敵", "ボス", "怪物", "モンスター"),
    # The board is drawn as coloured cells; the briefing calls a run of
    # them 「かたまり」. A request about the blocks is about those.
    "puzzle": ("ブロック", "コマ", "ピース"),
    # The page pushes a shot on every fire and paints each one
    # (`shots.forEach(s=>{cx.fillRect(s.x-1.5,s.y-8,3,10)})`), so a request
    # about the bullets is about something on the screen. 「敵」 already
    # passed through the briefing text; 「弾」 appears nowhere in it because
    # the how-to-play says 「連射」, which is why this needed saying here
    # rather than in the briefing (C-1528).
    "shooter": ("弾", "弾幕"),
}


def template_depicts(template: str, word: str) -> bool:
    """Does this template's page really put ``word`` on the screen?

    Read from what the page already tells the player it contains - the
    start screen's three briefing lines and the 操作説明 - rather than from
    a list written for this question. A page that stopped drawing its
    course would stop saying 「コースの終わりまで転がる」 in the same edit,
    so the two cannot drift the way C-1120's three hand-written word lists
    did.

    Containment rather than a word match, deliberately: 「宝」 has to find
    adventure's 「宝箱」, and Japanese gives no space to split on here. The
    error it can make is silence about a page that does draw something
    near enough to share a character - which is the safe direction for a
    note whose whole purpose is not to accuse the page falsely.
    """

    if not template or not word:
        return False
    entry = TEMPLATES.get(template)
    said = " ".join(BRIEFINGS.get(template, ()))
    if entry is not None:
        said = f"{said} {entry.how_to_play} {entry.default_title}"
    if word in said:
        return True
    return any(word == also for also in _ALSO_DEPICTED.get(template, ()))


def genre_fallback_note(message: str, template: str, title: str) -> str:
    """The admission that ``game.html`` fell back to the default template, or ""
    when it did not. One source of truth for the project summary (C-1285) and
    the production log (C-1605), so both say the same thing. No leading 「なお」:
    the summary prepends it; the log uses the sentence as a section body.

    Only the two cases the game path treats as a substitution fire, so a genre
    SIDRA does build never draws a caveat: a recognised but unsupported genre,
    and a request that named no genre whose subject the default cannot draw.
    """

    if not template:
        return ""
    default_title = TEMPLATES[template].default_title
    requested = detect_genre(message)
    if requested is not None and not requested.supported:
        return (
            f"「{requested.genre}」型はまだ作れないため、game.html は"
            f"代わりに既定の「{default_title}」型で作りました。"
        )
    if requested is None:
        undepicted = undepicted_subject(message, template, title)
        if undepicted:
            return (
                f"「{undepicted}」の題材を描く型はまだ無いため、game.html は"
                f"代わりに既定の「{default_title}」型で作りました。"
            )
    return ""


#: Removed only where they touch an end of the title - see
#: ``undepicted_subject``. 「の」 is here and is exactly why the removal has
#: to be anchored: taken from the middle it eats the one inside 「もの」.
_SUBJECT_FILLERS: tuple[str, ...] = (
    "みたいな", "みたいの", "っぽい", "風の", "みたい", "風", "の", "な",
)

#: Particles and other glue. A caveat that opens with one is quoting the
#: shape of the sentence rather than what it was about (C-1503).
_SUBJECT_GLUE: tuple[str, ...] = (
    "を", "が", "に", "へ", "と", "で", "の", "は", "も", "や", "から", "まで",
)


#: The particles that mark an argument of a verb, as opposed to 「の」 which
#: links two nouns. Used with ``_VERB_TAIL`` below and never alone - 「犬と猫」
#: is a list of two subjects and carries 「と」 (C-1524).
#:
#: 「の」 being absent is intent, not a measured boundary: a break test that
#: added it changed no result, because the pairing with ``_VERB_TAIL`` already
#: spares 「忍者のアクション」 (の, but ends in ン). Recorded as untested rather
#: than left looking covered.
_CASE_PARTICLES: tuple[str, ...] = ("を", "と", "が", "に", "へ", "で")

#: The う-row kana a Japanese verb ends its dictionary form with. Not a
#: morphological analyser - adding one is an open question in section E and
#: not a thing to decide inside a caveat - just the last character, which is
#: only consulted when a case particle is also present.
_VERB_TAIL: tuple[str, ...] = ("う", "く", "ぐ", "す", "つ", "ぬ", "ぶ", "む", "る")


def _is_whole_clause(subject: str) -> bool:
    """Whether this is a clause rather than the thing the request was about.

    C-1524. C-1503 stopped the caveat opening with a particle and C-1514
    stopped it closing with one, and 「巨大な敵と戦うゲームを作って」 still
    left 「敵と戦う」 - quoted back on the kaiju page, which is the
    fight-the-monster template, so the product said it could not draw the
    one thing it had drawn.

    **Both halves are needed, and each was measured.** A case particle alone
    is not enough: 「犬と猫」, 「海と山」, 「パンとご飯」 and 「宝石と鍵」 are
    lists of subjects and every one carries 「と」. A verb ending alone is not
    enough either - the item warned about this and it was right - because
    「走る」, 「光る」 and 「回る」 are subjects a request may name and they end
    like verbs. What no subject in the measured set does is *both*.

    The residual risk, stated rather than hidden: a list whose last noun ends
    in a う-row kana (「犬とさる」) reads as a clause and is silenced. Silence
    is the safe direction here - the caveat is an admission, and not making
    it costs less than making a false one.
    """

    if not subject:
        return False
    return any(p in subject for p in _CASE_PARTICLES) and subject.endswith(_VERB_TAIL)


def _is_quotable_subject(subject: str, request: str) -> bool:
    """Whether this may be quoted back to the operator as their own words.

    Two readings, each with a case behind it. It has to be **their** text -
    a contiguous run of the request, so no assembled phrase can appear in
    quotation marks - and it must not open with a particle, which is the
    shape of the sentence rather than what it was about.

    There is deliberately **no minimum length**. The item suggested rejecting
    a single character as debris, and that was tried: it silenced 「猫」 and
    「魚」, which are C-1205's own two examples and perfectly good subjects in
    Japanese. A one-character residue that IS debris is a particle, and the
    particle rule already has it.
    """

    if not subject or subject not in request:
        return False
    return not any(subject.startswith(glue) for glue in _SUBJECT_GLUE)


def _no_external_assets(html: str) -> bool:
    for match in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", html):
        if match.group(1).strip().lower().startswith(("http://", "https://", "//")):
            return False
    return "@import" not in html


#: Pad glyphs, matching what ``padButtons`` draws on the canvas for each key.
_PAD_GLYPH = {
    "ArrowLeft": "◀", "ArrowRight": "▶", "ArrowUp": "▲", "ArrowDown": "▼",
    " ": "A", "r": "R",
}
_PAD_DIRECTIONS = ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown")
_PAD_ACTIONS = (" ", "r")


def _touch_hint(script: str) -> str:
    """The mobile hint, naming the buttons this page's pad actually draws.

    C-1287: the hint was the constant 「◀ ▶ / A」 on every template, but the pad
    draws only the keys the game reads (PAD_ACTIVE, C-1244) - a fishing page has
    no arrows, racing has no A, and a puzzle has ▲▼ the constant never named. So
    the line told a mobile player about buttons that were not there and hid ones
    that were. The glyphs are read from the finished script's PAD_ACTIVE, the
    same source ``padButtons`` draws from, so the words and the buttons agree.
    """

    match = re.search(r"PAD_ACTIVE=new Set\((\[[^\]]*\])\)", script)
    active = set(json.loads(match.group(1))) if match else set()
    directions = [_PAD_GLYPH[k] for k in _PAD_DIRECTIONS if k in active]
    actions = [_PAD_GLYPH[k] for k in _PAD_ACTIONS if k in active]
    groups = [" ".join(g) for g in (directions, actions) if g]
    if not groups:
        return "スマホでは画面のボタンで操作できます。"
    return "スマホでは画面のボタン（" + " / ".join(groups) + "）で操作できます。"


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
/* On a phone the control panel's buttons - skin picker, copy-result, key
 * remap, reset - were 24-32px tall, under the 48dp minimum the knowledge
 * base itself sets (game-design-notes.md #4) and the touch pad already
 * honours (C-1219). No panel sets a button height inline, so one rule
 * scoped to a coarse pointer raises every one of them; desktop keeps its
 * compact controls, and the pad draws in the canvas so it is untouched. */
/* The tuning panel's non-button controls - difficulty select, sliders, colour
 * picker, checkboxes - stayed 13-27px and rendered at a 13.3px font: too small
 * to tap and small enough to make iOS zoom the page on focus. A 16px font floor
 * stops the zoom (the ask page's C-1225 rule, one level along) and a taller box
 * clears a fingertip; the checkbox is enlarged directly (C-1234). Kept on one
 * line with the button rule first so the C-1219 checks still read it, and all
 * inside the coarse-pointer query so the desktop panel is left unchanged. */
@media (pointer:coarse){{button{{min-height:48px}}select,input{{font-size:16px}}select,input[type=number],input[type=text],input[type=color],input[type=range]{{min-height:44px}}input[type=checkbox]{{width:24px;height:24px}}}}
/* The how-to and the start briefing name keyboard keys (「← →」), which a
 * phone does not have; the on-screen pad appears only once play starts, so
 * before that a touch visitor is told to press keys they cannot (C-1229).
 * This line names the pad, shown only for a coarse pointer so the desktop
 * keyboard hint stays the whole story there. */
.touchhint{{display:none;margin:8px 0 0;font-size:13px;color:{t["subtle"]}}}
@media (pointer:coarse){{.touchhint{{display:block}}}}
/* §18: the canvas keeps its 720:320 ratio at any width, so a phone held
 * upright plays at about half the size on each side that the same phone
 * gives lying down - and the page never mentioned it (C-1415). Hidden here
 * and turned on by the script, which is the only place that also knows
 * whether the game has started; a second rule in this sheet deciding the
 * same element is how the two come to disagree. */
.rotatehint{{display:none;margin:8px 0 0;font-size:13px;color:{t["subtle"]}}}
/* §18 事実 2: the URL bar and this page's own margins take about 40% of a
 * phone's screen, and fullscreen takes it back - but only for somebody who
 * asked (C-1416). Hidden here and shown by the script, which is the only
 * place that knows whether this browser will honour the request; a button
 * that opens nothing is worse than no button. The wrapper is what goes
 * fullscreen rather than the canvas, so the way back goes with it. */
.stagewrap{{display:block}}
.stagewrap:fullscreen{{display:flex;flex-direction:column;align-items:center;
 justify-content:center;background:{t["bg"]}}}
.stagewrap:fullscreen canvas{{width:100vw;max-width:100vw;max-height:88vh;
 border:0;border-radius:0}}
.fullbtn{{display:none;margin:8px 0 0;font-size:13px;padding:6px 12px;
 color:{t["text"]};background:{t["raised"]};border:1px solid {t["border"]};
 border-radius:{t["radius_tight"]};cursor:pointer}}
</style></head>
<body><main>
<h1>{escape(title)}</h1>
<p class="tag">{escape(tagline)}</p>
<div class="stagewrap" id="{FULL_WRAP_ID}">
<canvas id="stage" width="720" height="320"></canvas>
<button class="fullbtn" id="{FULL_BUTTON_ID}" type="button">{escape(FULL_LABEL)}</button>
</div>
<p class="rotatehint" id="{ROTATE_ID}">{escape(ROTATE_TEXT)}</p>
<p class="how">{escape(how)}</p>
<p class="touchhint">{_touch_hint(script)}</p>
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
            # Right on top of the remap wrapper, before anything registers
            # a keyup: focus loss releases held keys (§22, C-1373). It
            # hears keys in the spelling remap already translated, so its
            # synthetic keyups feed the handlers directly without being
            # translated twice.
            + FOCUS_PREAMBLE
            # The skins before the panel: TUNE_ACCENT is resolved through
            # skinAccent, so the colour a template paints with is the one
            # the player earned unless they picked one by hand (C-1109).
            + skin_preamble_for(key)
            # Then the panel: every preamble after it, and every template,
            # paints with TUNE_ACCENT and reads its numbers through tuneNum.
            + TUNE_PREAMBLE
            # After the panel (it reads the switch) and before anything
            # that uses SEED_TOKEN, which is every template body.
            + daily_preamble(key)
            # Before the gate, which is what takes the line away: the
            # element has to have been found by the time a press can
            # happen, and gateStart is the only caller (C-1415).
            + rotate_preamble()
            # Beside it and for the same reason (C-1416): both are page
            # chrome around the canvas, both are shown only where they
            # work, and neither may be reached before the elements exist.
            + fullscreen_preamble()
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
            # Why a go ended (C-1409), defined before the round so the
            # result strip can call it. Its expressions name the template's
            # own counters, which exist by the time the strip is drawn.
            + recap_preamble_for(key)
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
        # C-1414: whether this template plays itself behind its own title,
        # and the call that starts a fresh demo go. Both come from the one
        # table in attract.py, so an unwired template cannot be half-wired:
        # false here means the gate's demo branch is unreachable, and the
        # substituted reset is empty.
        .replace("ATTRACT_WIRED_TOKEN", "true" if attract_wired(key) else "false")
        .replace("ATTRACT_RESET_TOKEN", attract_reset_call(key))
        .replace("ATTRACT_PILOT_TOKEN", attract_pilot_call(key))
        .replace("ATTRACT_SLICE_TOKEN", str(attract_slice_frames(key)))
        # Read once, at load: nothing may shift under a player mid-round.
        .replace("SPEED_TOKEN", f"adaptSpeed(tuneNum('speed',{speed}))")
        # C-1404 (b): difficulty scales scope, not only speed - easy runs
        # fewer laps so the gentlest rung can actually beat the sixty-second
        # clock while every rung keeps a losing path against the clock for
        # weak driving at gentler panel speeds. Only racing carries the
        # token; every other template is byte-for-byte unaffected.
        .replace("LAPS_TOKEN", str(RACING_LAPS.get(difficulty, 3)))
        # C-1420: what one gate pays before the run's multiplier. Only
        # marble carries the token, so every other template is
        # byte-for-byte unaffected by the replace.
        .replace("GATE_BASE_TOKEN", str(MARBLE_GATE_BASE))
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
        # C-1130: the shared chrome (the round banner, the result strip)
        # used to paint itself in the dark theme's own ink whatever palette
        # the page was in, so the paper theme got a near-black slab across a
        # white page - the one thing on screen that did not agree with the
        # request. INK is the theme's text colour and SCRIM its background,
        # which is what a veil over the game should be made of.
        .replace("INK_TOKEN", theme.tokens["text"])
        .replace("SCRIM_TOKEN", theme.tokens["bg"])
        .replace("ADV_PAL_TOKEN", json.dumps([list(p) for p in ADVENTURE_PALETTE]))
        .replace("KAIJU_PAL_TOKEN", json.dumps([list(p) for p in KAIJU_PALETTE]))
        .replace("RACING_PAL_TOKEN", json.dumps([list(p) for p in RACING_PALETTE]))
        .replace("PLAT_PAL_TOKEN", json.dumps([list(p) for p in PLATFORMER_PALETTE]))
        .replace("SHOOTER_PAL_TOKEN", json.dumps([list(p) for p in SHOOTER_PALETTE]))
        .replace("MARBLE_PAL_TOKEN", json.dumps([list(p) for p in MARBLE_PALETTE]))
        .replace("FISHING_PAL_TOKEN", json.dumps([list(p) for p in FISHING_PALETTE]))
        .replace("CATCH_PAL_TOKEN", json.dumps([list(p) for p in CATCH_PALETTE]))
        .replace("DUEL_PAL_TOKEN", json.dumps([list(p) for p in DUEL_PALETTE]))
        .replace("PUZZLE_PAL_TOKEN", json.dumps([list(p) for p in PUZZLE_PALETTE]))
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
            # LAPS_TOKEN inside a briefing is filled from the same table the
            # racing script's own LAPS comes from (C-1625), after the script
            # chain's own LAPS_TOKEN pass has already run.
            json.dumps(list(BRIEFINGS.get(key, ())), ensure_ascii=False).replace(
                "LAPS_TOKEN", str(RACING_LAPS.get(difficulty, 3))
            ),
        )
    )
    # The pad draws only the buttons this page reads (C-1244). Computed on the
    # finished script - wrappers above add restart's `r` and some templates'
    # space - and prepended so PAD_ACTIVE exists before the first draw.
    script = pad_active_declaration(script) + script
    title = title_override or _title_from(request, spec.default_title)
    # The subtitle showed 「テンプレート {key}」 - the internal template key, in
    # English, on a Japanese page (C-1259). The genre vocabulary already maps
    # every buildable key to a Japanese label, so name the genre instead; the
    # key falls through only if some template ever lacks a label.
    genre_label = next((label for label, tkey, _words in GENRES if tkey == key), key)
    tagline = f"難易度 {difficulty} / ジャンル {genre_label}"
    asked_title = title
    # The third layer of C-1121's lie, and the one that outlives the answer:
    # the summary says 「対戦格闘型はまだ作れない」 and the file it hands over
    # is called 「対戦格闘」. The operator's own words are usually the better
    # title and claim nothing - but when those words name a genre this
    # product just declined, they are a claim, and the page keeps making it
    # long after the sentence has scrolled away. Only for a decline: a
    # buildable genre is still titled in the words that asked for it.
    declined = detect_genre(request)
    if not title_override and declined is not None and not declined.supported:
        title = spec.default_title
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
    return GeneratedGame(
        key,
        title,
        tagline,
        difficulty,
        html,
        asked_title=asked_title if asked_title != spec.default_title else "",
        renamed=bool(named),
    )


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
