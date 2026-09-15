"""Asked to turn the page's dials, does the product say where they are?

C-1861. The generated page ships a tuning panel - volume, music volume,
haptic, reduce-motion - built by C-1408, C-1697, C-1413 and C-1393. Somebody
who has just made a game and asks for any of them got one of three wrong
answers, depending on wording:

* 「動きを減らして」「エフェクトを減らして」 → 「『動き』は増減できません。この型で
  増減できるのは『敵』（敵の数）です」 - false: the switch is on the page;
* 「音量を下げて」「揺れを弱くして」 → the list of revisable parameters, which does
  not include them;
* 「振動を切って」 → the no-evidence wall, telling a reader asking about a
  setting to have a repository ingested - C-1261 and C-1814's hole, reopened
  by the panel's own vocabulary.

The same 「adjust this」 got three different misses, which is C-1847's symptom
exactly; the difference is that here the feature EXISTS. So nothing new is
built and nothing is written: a panel value is this viewer's setting, kept in
their browser, and editing the file would change what everyone else sees when
they open the same page. What was missing was the sentence.

The offered dials are read off the page's real schema, so a dial added to the
panel joins the answer by existing - the lesson C-1848 and C-1850 both cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import asks_about_panel, panel_setting_labels
from sidra_ai.creation.tuning import VIEWER_SETTING_KEYS
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: One per way a person names a dial, each measured wrong on 2026-09-15.
PANEL_REQUESTS: tuple[str, ...] = (
    "さっきのゲームの動きを減らして",
    "さっきのゲームの音量を下げて",
    "さっきのゲームの振動を切って",
    "さっきのゲームの揺れを弱くして",
    "さっきのゲームのエフェクトを減らして",
)

#: Requests that must keep the answers they had. 「音を消して」 is C-1814's own
#: example of a feature request; the rest are real revisions and a deletion.
NOT_PANEL: dict[str, str] = {
    "さっきのゲームの音を消して": "revision_change",
    "さっきのゲームを消して": "delete_unsupported",
    # C-1802's own check caught this one while this item was being written:
    # the panel's music row is a VOLUME dial, so 「BGMを変えて」 - change the
    # tune - is not something it can do, and pointing at the panel would be
    # the same false 「yes」 this item exists to stop being a false 「no」.
    # 「BGMの音量を下げて」 still reaches the panel, through 音量.
    "それのBGMを変えて": "revision_change",
}


@dataclass(frozen=True)
class PanelSettingResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_chat_panel_setting_points_at_the_panel() -> PanelSettingResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("sidra-c1861-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("迷宮を冒険するゲームを作って")
    before = {path.name for path in (root / "artifacts").iterdir()}

    answers = {request: service.chat(request) for request in PANEL_REQUESTS}
    after = {path.name for path in (root / "artifacts").iterdir()}

    # --- (A) nothing was written -----------------------------------------
    #     First, because a panel value belongs to the viewer: writing it into
    #     the file would change what the next reader sees.
    add(before == after, f"A: files changed: {sorted(after ^ before)}")

    # --- (B) every phrasing gets the same, true answer --------------------
    wrong = {
        request: result.get("refusal")
        for request, result in answers.items()
        if result.get("refusal") != "panel_setting"
    }
    add(not wrong, f"B: answered as something else: {wrong}")

    # --- (C) and the answer says where the control is ---------------------
    add(all("調整パネル" in (r.get("answer") or "") for r in answers.values()),
        "C: the answer does not say where the panel is")

    # --- (D) it offers every dial the page actually has -------------------
    #     Read from the schema, not written here: a check with its own list
    #     would agree with itself while the panel moved on.
    dials = panel_setting_labels("adventure", "normal")
    add(len(dials) == len(VIEWER_SETTING_KEYS),
        f"D: the schema offered {dials}, not {len(VIEWER_SETTING_KEYS)} dials")
    for dial in dials:
        add(all(dial in (r.get("answer") or "") for r in answers.values()),
            f"D: the answer never offers 「{dial}」")

    # --- (E) it names what they asked about, unfolded ----------------------
    add("「動き」" in (answers["さっきのゲームの動きを減らして"].get("answer") or ""),
        "E: the answer does not quote the word that was asked about")
    add(not any("動キ" in (r.get("answer") or "") for r in answers.values()),
        "E: a folded spelling reached the reader")

    # --- (F) the neighbouring answers are untouched -----------------------
    for request, want in NOT_PANEL.items():
        got = service.chat(request).get("refusal")
        add(got == want, f"F: {request!r} now answers {got!r}, not {want!r}")

    # --- (G) and a real revision still works ------------------------------
    add(service.chat("さっきのゲームを難しくして").get("refused") is False,
        "G: a genuine revision stopped working")
    add(service.chat("さっきのゲームの敵を増やして").get("refused") is False,
        "G: the axis revision stopped working")

    # --- (H) the vocabulary does not swallow the neighbours ---------------
    add(not asks_about_panel("さっきのゲームの音を消して"),
        "H: 「音を消して」 was read as a panel dial")
    add(not asks_about_panel("さっきのゲームを難しくして"),
        "H: a difficulty change was read as a panel dial")

    return PanelSettingResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
