"""Deterministic, dependency-free backend.

This is the default so that ``pytest`` and ``sidra-api`` work on a clean
checkout with no model weights, no GPU, no network and no paid API. It does
not pretend to reason: it extracts the retrieved evidence and reports it with
citations, which is exactly what the pipeline plumbing needs to be tested
against.

Swap it for ``ollama``/``llama_cpp``/``transformers`` via
``SIDRA_MODEL_BACKEND`` once weights are available locally.
"""

from __future__ import annotations

import re

from sidra_ai.creation.evidence import plain_text
from sidra_ai.retrieval.search import tokenize
from sidra_ai.models.base import (
    GenerationRequest,
    GenerationResult,
    LocalModelAdapter,
    estimate_tokens,
)

#: A question containing any CJK character is treated as Japanese for the
#: canned no-evidence reply. Same ranges as retrieval tokenization.
_CJK = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")

#: Japanese punctuation and fullwidth/halfwidth forms - the CJK symbols block
#: (、。「」…) and the fullwidth block (？！（）, fullwidth Latin/digits,
#: halfwidth katakana). A question with no kana or kanji but written with
#: these is still Japanese input: 「OutputGuard？」 is a Japanese user asking,
#: and the old kana/kanji-only gate handed them an English reply, against
#: SYSTEM_PROMPT rule 6 (C-1231). An ASCII keyboard produces none of these,
#: so treating them as a Japanese signal does not pull English questions over.
_JA_PUNCT = re.compile(r"[　-〿＀-￯]")


def _is_japanese(text: str) -> bool:
    """True when the text carries any Japanese script *or* punctuation."""
    return bool(_CJK.search(text) or _JA_PUNCT.search(text))


#: A Latin letter - the mark of a question actually written in a Latin script.
_LATIN = re.compile(r"[A-Za-z]")


def _reply_in_japanese(text: str) -> bool:
    """Which language a reply takes, for SYSTEM_PROMPT rule 6.

    Japanese script or punctuation is Japanese. So is a question with no
    language at all - digits, symbols, emoji, or nothing: ``_is_japanese`` is
    false for it, but this product's readers are Japanese, and the English
    branch would hand them 「Run POST /v1/github/analyze」 (C-1248). English is
    reserved for a question actually written in a Latin script (one that has a
    Latin letter), so a genuine English or romaji question still gets English.
    """
    return _is_japanese(text) or not _LATIN.search(text)


#: Below this many characters a "sentence" is a label or list-marker
#: fragment (「D-CY4.」「A.」), not content a reader can act on.
_MIN_INFORMATIVE = 12

_BLOCK = re.compile(
    r"<<<SIDRA_DATA_BLOCK (?P<label>S\d+)>>>\n"
    r"source: (?P<citation>[^\n]*)\n"
    r"trust: (?P<trust>[^\n]*)\n"
    r"content:\n(?P<content>.*?)\n"
    r"<<<END_SIDRA_DATA_BLOCK (?P=label)>>>",
    re.DOTALL,
)


class EchoModelAdapter(LocalModelAdapter):
    """Summarizes retrieved blocks extractively, with citations."""

    backend = "echo"
    requires_paid_api = False

    def __init__(self, model: str = "sidra-local-v0", **options: object) -> None:
        super().__init__(model, **options)
        self.max_sentences_per_block = int(options.get("max_sentences_per_block", 2))

    def generate(self, request: GenerationRequest) -> GenerationResult:
        blocks = list(_BLOCK.finditer(request.data_context))

        if not blocks:
            question = request.user_message.strip()
            if _reply_in_japanese(question):
                # SYSTEM_PROMPT rule 6 - born from the 2026-08-27 incident -
                # says a Japanese question gets a Japanese answer, and this
                # canned text was the one reply that ignored it (C-1202). It
                # must open with a marker `grounding._NO_EVIDENCE_MARKERS`
                # recognizes at sentence start, and every later sentence must
                # start with an advisory prefix (別の/確認), so the honest
                # abstention still *counts* as one in the grounding eval.
                text = (
                    "現時点では十分な根拠がありません。資料を索引した範囲では、"
                    "この質問へ答えられる内容が見つかりませんでした。"
                    "別の言い方で質問し直すか、対象リポジトリの取り込み"
                    "（POST /v1/github/analyze）を管理者に依頼してください。\n\n"
                    f"確認した質問: {question}"
                )
            else:
                text = (
                    "No indexed evidence matched this question. "
                    "Rephrase the question, or ask your administrator to ingest "
                    "the relevant repositories (POST /v1/github/analyze).\n\n"
                    f"Question received: {question}"
                )
            return self._result(request, text, finish_reason="no_evidence")

        # The framing lines follow the question's language, same rule and
        # same reason as the no-evidence reply above (C-1202/C-1208): rule 6
        # holds for the successful path too, and this preamble opens every
        # answered Japanese question. The [S#] labels and excerpts between
        # them are untouched either way, so grounding's citation checks and
        # every excerpt-based judge read the same evidence.
        if _reply_in_japanese(request.user_message):
            preamble = (
                "索引済みリポジトリの DATA から回答します"
                "（抜粋・ローカル生成・外部 API 不使用）。"
            )
            footer = "引用した出典: "
        else:
            preamble = (
                "Answering from indexed repository DATA "
                "(extractive; local backend, no external API)."
            )
            footer = "Cited sources: "

        # Two files often carry the identical passage (a TODO copied into a
        # cycle report), so retrieval hands back two blocks with the same text
        # and the answer printed the paragraph twice - the reader reads it
        # again and it looks like two independent findings (C-1241). The full
        # excerpt is shown once; a later block with the same text points back
        # to where it was shown. The footer still lists every source, because
        # "both files say this" is a true and useful fact - only the re-reading
        # is dropped.
        # C-1808: the dedup key is the truncated `_lead` excerpt, not the full
        # block, so two DIFFERENT documents whose leads coincide (a shared intro,
        # distinct later sentences) collapse here. 「同じ内容」 (same content)
        # asserted the documents were identical - false for that case, and it hid
        # the later source's distinct text behind a false-sameness claim. The
        # note now claims only what the dedup actually compares: the excerpt shown
        # (「抜粋が同じ」 / "same excerpt as"). The full text of each source is in
        # its citation, where any difference is visible.
        same_note = "（{} と抜粋が同じ）" if _reply_in_japanese(request.user_message) else "(same excerpt as {})"
        lines = [preamble, ""]
        shown: dict[str, str] = {}
        for match in blocks:
            label = match.group("label")
            excerpt = self._lead(match.group("content"), request.user_message)
            lines.append(f"[{label}] {match.group('citation')}")
            prior = shown.get(excerpt) if excerpt else None
            if prior is not None:
                lines.append(f"    {same_note.format(prior)}")
            else:
                lines.append(f"    {excerpt}")
                if excerpt:
                    shown[excerpt] = label
            lines.append("")

        lines.append(
            footer
            + ", ".join(f"[{m.group('label')}] {m.group('citation')}" for m in blocks)
        )
        return self._result(request, "\n".join(lines).strip())

    # ------------------------------------------------------------------
    def _lead(self, content: str, query: str = "") -> str:
        # The corpus is Markdown, and a sentence-terminator split treats a
        # heading label (「## D-CY4.」) and a checkbox stub (「**A.」) as two
        # full sentences - the whole excerpt budget spent before any actual
        # content (C-1216). Flatten the markup the way generated documents
        # already do (C-1212; symbols only, every literal survives), and let
        # short fragments ride along without consuming a sentence slot.
        collapsed = plain_text(content)
        boundary = re.compile(r"[。！？]|[.!?](?=\s)")
        # C-1216: a leading Markdown heading is the section label the quoted
        # evidence sits under - the item id a reader greps for - so it rides
        # along as context. C-1825 opens the body on the answering sentence,
        # which can be below that heading; keep the heading as a prefix so the
        # reader still sees which section the answer came from.
        heading = ""
        heading_match = re.match(r"[ \t]*#{1,6}[ \t]+\S.*", content)
        if heading_match:
            heading = plain_text(heading_match.group(0)).strip()
        # C-1825: open the answer on the sentence whose terms best match the
        # question - the same relevance the citation excerpt already has
        # (C-1782/select_excerpt_span). With no query terms, or none that appear
        # anywhere, the head stays at the opening (0), which is the previous
        # behaviour, so ordinary answers are unchanged. A tie keeps the earliest
        # sentence, so a topic discussed from the start still opens at the start.
        head = 0
        terms = set(tokenize(query))
        if terms:
            best = 0
            span_start = 0
            for cut in [m.end() for m in boundary.finditer(collapsed)] + [len(collapsed)]:
                if cut <= span_start:
                    continue
                score = len(terms & set(tokenize(collapsed[span_start:cut])))
                if score > best:
                    best, head = score, span_start
                span_start = cut
        # Sentence boundaries by position, not by splitting on whitespace: the
        # old `(?<=[.。!?！？])\s+` required a space *after* the terminator, but
        # Japanese prose puts none after 「。」, so a whole 「…です。…です。」 block
        # counted as one sentence and the per-block budget never fired - the
        # answer dumped the entire block (to 400 chars) in the product's main
        # language (C-1518). A CJK terminator (。！？) ends a sentence on its own;
        # an ASCII terminator (.!?) only when whitespace follows, so 「3.14」 and
        # 「e.g.」 are not cut. Slicing the original preserves its spacing, so no
        # space is inserted between Japanese sentences that had none. The budget
        # is counted from ``head`` (the query-relevant opening above), so the
        # sentences shown are the answering one and what follows it.
        start = head
        informative = 0
        end = len(collapsed)
        for match in boundary.finditer(collapsed, head):
            cut = match.end()
            if len(collapsed[start:cut].strip()) >= _MIN_INFORMATIVE:
                informative += 1
                if informative >= self.max_sentences_per_block:
                    end = cut
                    break
            start = cut
        lead = collapsed[head:end].strip()
        # Prepend the section heading when relevance opened the body below it, so
        # the item id (C-1216) is not lost. If the body already begins with the
        # heading (head stayed at the top, or the heading matched the query),
        # nothing is added.
        if heading and head > 0 and not lead.startswith(heading):
            lead = f"{heading} {lead}".strip() if lead else heading
        return (lead[:400] + "...") if len(lead) > 400 else lead or "(empty)"

    def _result(
        self, request: GenerationRequest, text: str, finish_reason: str = "stop"
    ) -> GenerationResult:
        return GenerationResult(
            text=text,
            backend=self.backend,
            model=self.model,
            input_tokens_estimate=estimate_tokens(self.build_prompt(request)),
            output_tokens_estimate=estimate_tokens(text),
            finish_reason=finish_reason,
            metadata={"extractive": True, "cost_usd": 0.0},
        )
