"""Does a request whose one game verb is "jump" reach the platformer?

C-1220: the platformer template existed, but ``PLATFORMER_WORDS`` only held
the compound 「ジャンプアクション」, not the bare 「ジャンプ」. So
「猫がジャンプするゲームを作って」 detected no genre at all and fell to the
default fishing template - and because nothing was *substituted* (no genre
was ever detected), the summary carried no notice either. A jump game came
back as a fishing game, silently. Adding the bare jump cues to the one list
both the router and the honesty table read fixes routing and the summary at
once.

The checks route jump-shaped requests through the public ``choose_template``
/ ``detect_genre`` and confirm they land on the platformer, that a
shooter-with-jump still wins for the shooter (order protects it), and that
the default is no longer where a jump request ends up.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Requests whose only genre cue is a jump. Each must reach the platformer.
_JUMP_REQUESTS = (
    "猫がジャンプするゲームを作って",
    "ジャンプゲームを作って",
    "跳ねて進むゲーム",
    "穴を飛び越えるゲーム",
)

#: A jump that is scenery for a genre the request names outright. The named
#: genre must still win - including fishing/catch, which are matched before
#: the platformer's bare-jump cue precisely so 「魚が跳ねる釣り」 stays fishing.
_OTHER_GENRE_WITH_JUMP = (
    ("ジャンプで敵を撃つシューティングを作って", "shooter"),
    ("ジャンプしながら解くパズル", "puzzle"),
    ("魚が跳ねる釣りゲームを作って", "fishing"),
    ("跳ねる的をキャッチするゲーム", "catch"),
)


@dataclass(frozen=True)
class JumpRoutesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_jump_routes_to_platformer() -> JumpRoutesResult:
    from sidra_ai.creation.games import choose_template, detect_genre

    checks = 0
    failures: list[str] = []

    for request in _JUMP_REQUESTS:
        if choose_template(request) == "platformer":
            checks += 1
        else:
            failures.append(f"{request}: routed to {choose_template(request)}, not platformer")

    # The clearest one must also be a *detected* genre, so the summary names
    # it rather than silently substituting.
    named = detect_genre("猫がジャンプするゲームを作って")
    if named is not None and named.template == "platformer":
        checks += 1
    else:
        failures.append("a jump request is not a detected genre (summary would stay silent)")

    for request, expected in _OTHER_GENRE_WITH_JUMP:
        if choose_template(request) == expected:
            checks += 1
        else:
            failures.append(
                f"{request}: jump stole the route to {choose_template(request)}, expected {expected}"
            )

    return JumpRoutesResult(
        passed=not failures, checks_passed=checks,
        checks_total=len(_JUMP_REQUESTS) + 1 + len(_OTHER_GENRE_WITH_JUMP),
        failures=tuple(failures),
    )
