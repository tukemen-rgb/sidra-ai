"""C-1832: a request for three models hears that one was made.

One request builds one mesh. 「魚の3Dモデルを3つ作って」 titled its artifact
「魚3つ」 and said nothing - and with the shape available, the shape-default
note stayed silent too, so nothing anywhere mentioned the count.
"""

from __future__ import annotations

from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.creation.model3d_job import build_model3d_generator
from sidra_ai.creation.models3d import (
    MADE_PER_REQUEST,
    count_note,
    generate_model3d,
    requested_count,
)
from sidra_ai.evals.model3d_says_it_made_one import (
    evaluate_model3d_says_it_made_one,
)
from sidra_ai.evals.scratch import scratch_dir

_NOTE = "個数は指定できません"


def _summary(request: str) -> str:
    generate = build_model3d_generator(scratch_dir("sidra-c1832-test-"))
    return generate(request, detect_creation_intent(request)).summary or ""


def test_model3d_count_eval_passes():
    result = evaluate_model3d_says_it_made_one()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 8


def test_a_count_that_was_not_built_is_disclosed_in_both_places():
    request = "魚の3Dモデルを3つ作って"
    assert _NOTE in _summary(request)
    assert _NOTE in generate_model3d(request).preview_html


def test_a_request_with_no_count_adds_no_note():
    request = "魚の3Dモデルを作って"
    assert _NOTE not in _summary(request)
    assert _NOTE not in generate_model3d(request).preview_html


def test_the_count_actually_made_adds_no_note():
    assert _NOTE not in _summary("3Dモデルを1つ作って")


def test_the_note_coexists_with_the_shape_and_colour_disclosures():
    page = generate_model3d("赤い立方体を10個の3Dモデルで作って").preview_html
    assert _NOTE in page
    assert "依頼に合う形状が無かった" in page
    assert "依頼にあった色は今の配色に反映していません" in page


def test_a_number_that_is_not_a_count_is_not_a_request():
    assert requested_count("2026年の3Dモデルを作って") is None
    assert requested_count("魚の3Dモデルを3つ作って") == 3
    assert requested_count("船の3Dモデルを2体作って") == 2
    assert requested_count("100個の3Dモデル") == 100


def test_the_note_names_the_number_it_was_given():
    note = count_note("魚の3Dモデルを3つ作って", 2)
    assert "3 つ" in note and "2 体" in note
    assert count_note("魚の3Dモデルを作って") == ""
    assert count_note(f"3Dモデルを{MADE_PER_REQUEST}つ作って") == ""
