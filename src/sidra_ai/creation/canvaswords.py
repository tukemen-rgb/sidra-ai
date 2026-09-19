"""The words the page says, in both languages, in one table (C-1959).

Named for the canvas because that is where it started; C-1965 widened it
to the panels under the canvas, which are built by the page's own
JavaScript. One table, one injection and one set of guards was worth more
than a second mechanism with the same shape.

C-1956 put the page's frame into the language of the request and C-1957 the
start screen's three lines. What a player looks at for the whole of a go -
the HUD row, the clock badge, the banner that ends it, the result strip -
was still Japanese whatever was asked, because those words are written
straight into the JavaScript each module hands to the page.

Measured before it was written: a whole go of ``catch``, run to its end on
a recording context, draws eight distinct shapes. Seven carry Japanese, and
five of those come from ``round.py`` - they are on every template. So the
table is small, and most of it is shared.

**One table, both languages.** Every row here is a word the canvas draws,
with the Japanese it has always drawn and the English beside it. Nothing
here is a second table that could drift from a first: the Japanese column
IS what the pages used to carry as literals, moved rather than copied.

**Injected once.** ``words_js`` writes the chosen column into the page as
``CW``, ahead of every preamble, and the drawing code names ``CW.score``
where it used to carry 「得点」. A template that wants a word the table does
not have cannot silently fall back to Japanese - ``CW.whatever`` is
``undefined`` and the judge sees it.

**Guarded at import.** A row missing either language, or an English value
that still carries Japanese script, raises here rather than shipping a half
translated page (C-1945, C-1951, C-1957).
"""

from __future__ import annotations

import json
import re

from sidra_ai.creation.together import STORAGE_NOTE

#: ``key: (Japanese, English)``. Order is the order a player meets them:
#: the HUD row, then the clock, then the end of a go, then the strip.
CANVAS_WORDS: dict[str, tuple[str, str]] = {
    # --- the HUD row, while playing ---
    "score": ("得点", "score"),
    "caught": ("受け", "caught"),
    "missed": ("こぼし", "missed"),
    "move_hint": ("← → またはマウスで動かす", "← → or the mouse to move"),
    # --- the clock badge (round.py), on every template ---
    "time_left": ("のこり", "left"),
    # --- the banner that ends a go ---
    "time_up": ("ここまで", "Time's up"),
    "time_up_said": ("ここまで。", "Time's up."),
    "again": ("R / タップでもう一度", "R / tap to play again"),
    "copy": ("C / 結果をコピー", "C / copy the result"),
    # --- the result strip under it ---
    "best_new": ("自己ベスト更新", "a personal best"),
    "best": ("自己ベスト", "best"),
    "best_open": ("（自己ベスト ", " (best "),
    "best_close": ("）", ")"),
    "to_go_open": ("（あと ", " ("),
    "to_go_close": ("）", " to go)"),
    "daily": ("今日の挑戦", "today's run"),
    "day_open": ("（", " ("),
    "day_close": (" 日目）", " days running)"),
    "recent": ("直近", "recent"),
    "unlock_open": ("新しい見た目「", "a new look, "),
    "unlock_close": ("」が開きました", ", is open"),
    # --- fishing (C-1960) ---
    "fishing_hint": ("SPACE / クリックで合わせる", "SPACE / click to time it"),
    "catches": ("釣果", "catches"),
    "crit": ("会心", "perfect"),
    "bullseye": ("ど真ん中。会心。", "Dead centre. Perfect."),
    "hooked": ("かかった。", "Hooked."),
    "got_away": ("逃げられた。", "It got away."),
    # --- puzzle (C-1960) ---
    "hammers": ("つち", "hammers"),
    "clump_open": ("このかたまり ", "this clump: "),
    "cant_clear": ("ここは消せない", "this one cannot be cleared"),
    "all_cleared": ("全部消えた。", "All cleared."),
    "no_moves": ("もう消せる手がない。", "No moves left."),
    "again_space_r": (" / SPACE か R でもう一度", " / SPACE or R to play again"),
    # --- platformer (C-1960) ---
    "gems": ("宝石", "gems"),
    "falls": ("落下", "falls"),
    "lamp_on": ("  灯籠 点", "  lantern lit"),
    "reach_the_flag": ("足場を渡って、旗まで。", "Cross the platforms to the flag."),
    "lamp_lit": ("灯籠がともった。落ちてもここから。",
                 "The lantern is lit. A fall puts you back here now."),
    "lamp_cost_open": ("灯籠は宝石 ", "the lantern lights for "),
    "lamp_cost_mid": (" 個で点く（いま ", " gems (you have "),
    "lamp_cost_close": (" 個）。", ")."),
    "back_to_lamp": ("灯籠まで戻された。", "Back to the lantern."),
    "back_to_start": ("足場のはじめに戻された。", "Back to the first platform."),
    "light_reached": ("灯りは旗までとどいた。", "The light reached the flag."),
    "again_r_tap": (" / R かタップでもう一度", " / R or tap to play again"),
    # --- marble (C-1960) ---
    "score_kana": ("スコア", "score"),
    "gates": ("ゲート", "gates"),
    "distance": ("距離", "distance"),
    "hit_block": ("ブロックに当たった。", "You hit a block."),
    "course_done": ("コースを走り切った。", "You finished the course."),
    # --- kaiju (C-1960) ---
    "cycles": ("周期", "cycles"),
    "legs": ("脚", "legs"),
    "kaiju_silent": ("巨獣、沈黙。", "The kaiju falls silent."),
    "squad_back": ("部隊は退いた。", "The squad pulled back."),
    "again_key": ("R でもう一度", "R to play again"),
    # --- the counters English does not say (C-1960) ---
    #
    # 「個」 and 「回」 count things a number already counts in English, so
    # their English column is deliberately empty. An empty value is a
    # mistake everywhere else, so every row that means to be empty is
    # named in EMPTY_IN_ENGLISH below and the guard checks the two agree.
    "n_things": (" 個", ""),
    "n_times": (" 回", ""),
    # --- duel (C-1962) ---
    "duel_won": ("勝利。ひかりが押し切った。", "You win. The light broke through."),
    "duel_lost": ("敗北。ひかりが押し切られた。", "You lose. The light was pushed back."),
    "misfire_open": ("暴発。", "Misfire. "),
    "misfire_close": (" 秒動けない", "s before you can move"),
    "they_misfired": ("相手が暴発した", "they misfired"),
    "opponent": ("相手: ", "opponent: "),
    "style_quick": ("早撃ち型", "the quick draw"),
    "style_charge": ("溜め型", "the slow charge"),
    "pushing": ("押し合い。SPACE 連打で押し返す。", "A push. Mash SPACE to push back."),
    "again_space": ("SPACE / タップでもう一度", "SPACE / tap to play again"),
    # --- racing (C-1962) ---
    "on_road": ("走行", "on the road"),
    "off_road": ("コース外", "off the road"),
    "goal": ("ゴール。", "Finished."),
    "near_miss": ("  ニアミス ", "  near misses "),
    # --- shooter (C-1962) ---
    # Named "nth_wave" rather than "wave": the page reads it as
    # ``CW.wave_open``, and the audio judge looks for ".wav" in the page to
    # catch a template that references a sound file. C-1962 measured that
    # collision - creation_game_audio dropped 10 -> 9 with the reason
    # "shooter: references an audio file" and no audio file anywhere.
    "nth_wave_open": ("  第 ", "  wave "),
    "nth_wave_close": (" 波", ""),
    "kills": ("撃墜", "kills"),
    "graze": ("かすり", "grazes"),
    "shot_down_open": ("撃墜 ", "you shot down "),
    "shot_down_mid": (" 機・得点 ", " of them, for "),
    "shot_down_close": ("。", " points."),
    "again_space_r_tap": ("SPACE か R、タップでもう一度", "SPACE, R or a tap to play again"),
    # --- adventure (C-1964) ---
    #
    # The narration. Facts about what just happened and what is needed
    # next, which is why it can be translated at all: nothing here is a
    # turn of phrase somebody chose for its sound.
    "hero_wakes": ("ぼうしの勇者、めざめる。", "The hero in the hat wakes."),
    "found_gem": ("草のかげに宝石があった。", "A gem was hidden in the grass."),
    "chest_locked": ("鍵がかかっている。洞窟の敵が持っているらしい。",
                     "It is locked. The cave's enemy seems to hold the key."),
    "guard_alive": ("番人が生きている限り、宝箱は開かない。",
                    "The chest will not open while the guardian lives."),
    "tablet_hint": ("「東の洞窟の敵が鍵を守っている。祭壇の宝を頼む。」",
                    "\"The enemy in the east cave guards the key. The altar's "
                    "treasure is yours to find.\""),
    "shrine_full": ("祠は満ち足りている。ハートはもう増えない。",
                    "The shrine is content. No more hearts to give."),
    "shrine_took": ("祠が宝石を受け取った。ハートが増えた。",
                    "The shrine took the gems. One more heart."),
    "shrine_wants_open": ("祠は宝石を 3 個ほしがっている（いま ",
                          "the shrine wants 3 gems (you have "),
    "gems_now_close": (" 個）。", ")"),
    "path_opened": ("わき道が開いた。", "A side path opened."),
    "path_cost_open": ("宝石 2 個で開きそうだ（いま ",
                       "2 gems would open it (you have "),
    "stone_open": ("石碑「", "the stone reads: \""),
    "stone_close": (" の順に、洞窟の印を叩け」",
                    " - strike the cave's marks in that order\""),
    "guard_fell": ("番人は崩れ落ちた。祭壇が静まりかえる。",
                   "The guardian falls. The altar goes quiet."),
    "guard_faster": ("番人の足が速くなった。", "The guardian moves faster now."),
    "marks_quiet": ("印はもう静かだ。", "The marks are quiet now."),
    "seal_broke_key": ("封が解けて、鍵が転がり出た。",
                       "The seal breaks and a key rolls out."),
    "seal_broke": ("封が解けた。", "The seal breaks."),
    "mark_rang_open": ("印が低く鳴った（", "the mark rings low ("),
    "mark_rang_close": ("）。", ")"),
    "marks_wrong": ("印は沈黙した。順が違う。",
                    "The marks fall silent. That was the wrong order."),
    "found_charm": ("護符を見つけた。一度だけ身代わりになる。",
                    "You found a charm. It will take one hit for you."),
    "got_key": ("鍵を手に入れた。", "You have the key."),
    "charm_broke": ("護符が砕けて、身代わりになった。",
                    "The charm shattered and took the hit."),
    "ouch": ("いたい。", "That hurt."),
    "heavy_hit": ("重い一撃。", "A heavy hit."),
    "monument": ("碑", "stone"),
    "has_key": ("  鍵あり", "  key"),
    "has_charm": ("  護符", "  charm"),
    "adventure_win": ("宝箱をあけた。冒険の勝利。",
                      "The chest is open. The adventure is won."),
    "adventure_over": ("ちからつきた。", "Your strength gave out."),
    "charm_label_open": (" / 護符 ", " / charm "),
    "charm_yes": ("あり", "yes"),
    "charm_no": ("なし", "no"),
    "again_r_tap_retry": ("R か タップでやり直す", "R or tap to try again"),
    "again_r_tap_more": (" / R か タップでもう一度", " / R or tap to play again"),
    # --- adventure's three cave marks (C-1964) ---
    #
    # Drawn one glyph to a tile, so the English column is a symbol rather
    # than a word: "moon" does not fit where 「月」 fits, and the mark has
    # to stay readable at tile size. The stone names them in the same
    # glyphs, so the order a player reads is the order they strike.
    "mark_moon": ("月", "☾"),
    "mark_star": ("星", "★"),
    "mark_sun": ("日", "☀"),
    # --- adventure's three rooms (C-1964) ---
    "room_forest": ("森のはずれ", "the forest edge"),
    "room_cave": ("ひかり苔の洞窟", "the glowmoss cave"),
    "room_altar": ("風の祭壇", "the altar of wind"),
    # --- the panels under the canvas (C-1965) ---
    #
    # Built by the page at load time, so they are neither the HTML frame
    # (C-1956) nor the canvas (C-1959..C-1964). They are what a player
    # touches: the keys, the looks, the tuning, the copy button.
    "keys_panel": ("キー設定", "Keys"),
    "keys_default": ("既定のまま", "unchanged"),
    "keys_assigned": ("割り当て: ", "set to: "),
    "keys_press": ("キーを押して変更", "press a key to change"),
    "keys_waiting": ("どれかキーを押してください…", "press any key..."),
    "keys_reset": ("キーを既定に戻す", "reset the keys"),
    "looks_panel_open": ("見た目（累計 ", "Looks (played "),
    "looks_panel_close": ("）", ")"),
    "looks_note": ("遊んだぶんだけ色が増えます。強さは変わりません。",
                   "Play more, unlock more colours. None of them change the game."),
    "looks_to_go_open": ("（あと ", " ("),
    "looks_to_go_close": ("）", " to go)"),
    "tuning_panel": ("調整", "Settings"),
    "tuning_reset": ("既定に戻す", "reset"),
    "contrast_worn": ("着ている色は", "the colour worn is "),
    "contrast_chosen": ("選んだ差し色は", "the accent chosen is "),
    "contrast_measured": ("背景に対し ", " against the background, "),
    "contrast_floor": (":1 でした。文字が読めなくなるので ",
                       ":1. Text would stop being readable, so it is drawn at a "
                       "near lightness that meets "),
    "contrast_drawn": (":1 を満たす近い明るさ（", ":1 ("),
    "contrast_close": ("）で描いています。", ")."),
    "copy_result": ("結果をコピー", "copy the result"),
    "copied": ("コピーしました", "copied"),
    "now_manual": ("今の調整: 手動（自分で設定した値）",
                   "Now: your own settings"),
    "now_eased_open": ("今の調整: 1 段やさしく（", "Now: one step easier ("),
    "now_eased_close": (" 連敗のため。勝てば戻ります）",
                        " losses in a row; a win puts it back)"),
    "now_standard": ("今の調整: 標準", "Now: standard"),
    # The Japanese is imported, not typed again: C-1342 gave that sentence
    # one home and a copy here would be a second one (its own test caught
    # exactly that when C-1965 first wrote it out).
    "storage_note": (STORAGE_NOTE, "kept on this device (a browser may clear it)"),
    "note_open": ("（", " ("),
    "note_close": ("）", ")"),
    # --- the line a player pastes somewhere else (C-1965) ---
    #
    # This one leaves the page, so the language it is written in is the
    # language of wherever it lands.
    "todays": ("今日の", "today's "),
    "auto_eased": ("難度自動緩和", "difficulty eased automatically"),
    "mark_join": ("・", ", "),
    "personal_best": (" 自己ベスト", " personal best"),
}

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: The rows whose English is meant to be empty: Japanese counters that a
#: number says by itself in English. Declared rather than allowed, so a row
#: that simply never got its English still raises.
EMPTY_IN_ENGLISH = frozenset({"n_things", "n_times", "nth_wave_close"})

_EMPTY = sorted(
    k for k, v in CANVAS_WORDS.items()
    if not v[0] or (not v[1] and k not in EMPTY_IN_ENGLISH)
)
_UNTRANSLATED = sorted(k for k, v in CANVAS_WORDS.items() if _JAPANESE.search(v[1]))
_DECLARED_BUT_FILLED = sorted(
    k for k in EMPTY_IN_ENGLISH if k not in CANVAS_WORDS or CANVAS_WORDS[k][1]
)

if _EMPTY or _UNTRANSLATED or _DECLARED_BUT_FILLED:  # pragma: no cover
    raise RuntimeError(
        f"canvaswords.CANVAS_WORDS has empty rows {_EMPTY}, still carries "
        f"Japanese in the English column of {_UNTRANSLATED}, and declares "
        f"{_DECLARED_BUT_FILLED} empty while they are not"
    )


def words_js(*, in_japanese: bool = True) -> str:
    """The chosen column, as the ``CW`` the page's drawing code reads."""

    column = {key: pair[0 if in_japanese else 1] for key, pair in CANVAS_WORDS.items()}
    return "const CW=" + json.dumps(column, ensure_ascii=False) + ";\n"


_SAY_LITERAL = re.compile(r"say\('([^']+)'\)")
_SAY_WORD = re.compile(r"say\(CW\.(\w+)\)")


def said_lines(script: str, *, in_japanese: bool = True) -> list[str]:
    """Every whole line the page's ``say()`` can put on screen.

    Before C-1960 a reader could find these by looking for ``say('...')``
    in the page, and two test files did exactly that. Now a template says
    ``say(CW.lamp_lit)`` instead, so the same question has to be asked of
    the table as well - otherwise a template that still speaks looks mute,
    which is how a reading-speed test can pass by measuring nothing.

    Composed calls (a ternary, or a sentence built around a number) are
    left out here exactly as they were left out before: this returns the
    lines that are one whole string, which is what the callers measure.
    """

    column = 0 if in_japanese else 1
    lines = list(_SAY_LITERAL.findall(script))
    lines += [
        CANVAS_WORDS[key][column]
        for key in _SAY_WORD.findall(script)
        if key in CANVAS_WORDS
    ]
    return lines


__all__ = ["CANVAS_WORDS", "EMPTY_IN_ENGLISH", "said_lines", "words_js"]
