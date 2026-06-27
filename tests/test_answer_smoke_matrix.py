from __future__ import annotations

import json

from cipp_contracts.answer.report_answer_smoke_matrix import (
    ANSWER_SMOKE_TOPICS,
    CORE_TOPICS,
    GUIDANCE_TOPICS,
    AnswerSmokeTopic,
    binding_law_claims_count,
    build_answer_smoke_matrix,
    hallucination_guard,
    markdown_safety,
    render_report_markdown,
    write_report,
)


def packet(status: str = "ok", coverage: str = "ok") -> dict[str, object]:
    return {
        "retrieval_status": status,
        "evidence_coverage_status": coverage,
        "detected_topics": ["payment"],
    }


def answer(
    status: str = "answered",
    llm_used: bool = False,
    expert_guidance: bool = False,
    sources: int = 1,
) -> dict[str, object]:
    source_class = "expert_guidance" if expert_guidance else "retrieval_evidence"
    return {
        "answer_status": status,
        "short_answer": "Asiantuntijaohjeen perusteella asia kannattaa selvittää." if expert_guidance else "Fixture answer.",
        "key_points": ["Fixture point."],
        "source_based_notes": [
            "Asiantuntijaohjeen katkelma: lyhyt fixture."
            if expert_guidance
            else "Lähdekatkelma: fixture text."
        ],
        "missing_user_case_fields": ["apartments_count"] if status == "partial" else [],
        "uncertainties": [
            "Tämä kohta perustuu asiantuntijaoppaaseen. Sitova tulkinta pitää varmistaa varsinaisesta lakitekstistä, yhtiöjärjestyksestä, sopimuksesta tai asiantuntijalta."
        ]
        if expert_guidance or status == "partial"
        else [],
        "recommended_next_questions": ["Fixture next question?"],
        "sources": [
            {
                "source_class": source_class,
                "snippet": "fixture text",
                "document_type": "legal_guidance_pipe_renovation" if expert_guidance else "contract",
            }
            for _ in range(sources)
        ],
        "llm_used": llm_used,
        "generation_mode": "deterministic_source_grounded",
    }


def markdown(answer_doc: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Source-grounded answer",
            str(answer_doc["short_answer"]),
            "\n".join(str(item) for item in answer_doc["key_points"]),
            "\n".join(str(item) for item in answer_doc["source_based_notes"]),
            "\n".join(str(item) for item in answer_doc["uncertainties"]),
        ]
    )


def test_smoke_matrix_contains_20_topics() -> None:
    assert len(ANSWER_SMOKE_TOPICS) == 20


def test_core_topics_count_is_10() -> None:
    assert len(CORE_TOPICS) == 10


def test_guidance_topics_count_is_10() -> None:
    assert len(GUIDANCE_TOPICS) == 10


def test_each_topic_gets_topic_status() -> None:
    report = build_answer_smoke_matrix(lambda _question: (packet(), answer(), markdown(answer())))

    assert {row["topic_status"] for row in report["topics"]} == {"pass"}


def test_summary_counts_pass_partial_fail() -> None:
    answers = iter(
        [
            (packet(), answer(), markdown(answer())),
            (packet(status="partial", coverage="partial"), answer(status="partial"), markdown(answer(status="partial"))),
            (packet(status="no_results", coverage="no_text_context"), answer(status="insufficient_evidence", sources=0), ""),
        ]
    )

    report = build_answer_smoke_matrix(
        lambda _question: next(answers),
        topics=(
            AnswerSmokeTopic("pass_topic", "pass?", "core"),
            AnswerSmokeTopic("partial_topic", "partial?", "core"),
            AnswerSmokeTopic("fail_topic", "fail?", "core"),
        ),
    )

    assert report["summary"]["passed"] == 1
    assert report["summary"]["partial"] == 1
    assert report["summary"]["failed"] == 1


def test_release_candidate_false_if_any_topic_fails() -> None:
    report = build_answer_smoke_matrix(
        lambda _question: (packet(), answer(llm_used=True), markdown(answer(llm_used=True))),
        topics=(AnswerSmokeTopic("bad", "bad?", "core"),),
    )

    assert report["summary"]["release_candidate"] is False


def test_release_candidate_true_without_failures() -> None:
    report = build_answer_smoke_matrix(
        lambda _question: (packet(), answer(), markdown(answer())),
        topics=(AnswerSmokeTopic("ok", "ok?", "core"),),
    )

    assert report["summary"]["release_candidate"] is True


def test_llm_used_true_causes_fail() -> None:
    report = build_answer_smoke_matrix(
        lambda _question: (packet(), answer(llm_used=True), markdown(answer(llm_used=True))),
        topics=(AnswerSmokeTopic("llm", "llm?", "core"),),
    )

    assert report["topics"][0]["topic_status"] == "fail"


def test_expert_guidance_does_not_become_binding_law() -> None:
    safe_answer = answer(expert_guidance=True)
    report = build_answer_smoke_matrix(
        lambda _question: (packet(), safe_answer, markdown(safe_answer)),
        topics=(AnswerSmokeTopic("guidance", "guidance?", "guidance"),),
    )

    assert report["topics"][0]["topic_status"] == "pass"
    assert report["topics"][0]["binding_law_claims_count"] == 0


def test_markdown_safety_finds_windows_path() -> None:
    status, warnings = markdown_safety("C:\\secret\\file")

    assert status == "failed"
    assert warnings


def test_markdown_safety_finds_project_name() -> None:
    status, warnings = markdown_safety("Referenssikoivu")

    assert status == "failed"
    assert warnings


def test_hallucination_guard_finds_invented_amount() -> None:
    unsafe_answer = answer()
    unsafe_markdown = markdown(unsafe_answer) + "\nUrakka maksaa 12345 euroa."

    status, findings = hallucination_guard(unsafe_answer, unsafe_markdown)

    assert status == "failed"
    assert findings


def test_binding_law_claims_are_counted() -> None:
    assert binding_law_claims_count("Laki määrää tämän.") == 1


def test_json_output_writes(tmp_path) -> None:
    report = build_answer_smoke_matrix(
        lambda _question: (packet(), answer(), markdown(answer())),
        topics=(AnswerSmokeTopic("ok", "ok?", "core"),),
    )
    output = tmp_path / "answer_smoke.json"

    write_report(report, output, None)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "answer_smoke_matrix"


def test_markdown_output_renders(tmp_path) -> None:
    report = build_answer_smoke_matrix(
        lambda _question: (packet(), answer(), markdown(answer())),
        topics=(AnswerSmokeTopic("ok", "ok?", "core"),),
    )
    output_md = tmp_path / "answer_smoke.md"

    write_report(report, None, output_md)

    assert output_md.read_text(encoding="utf-8").startswith("# Answer Composer Smoke Matrix")
    assert "# Answer Composer Smoke Matrix" in render_report_markdown(report)


def test_tests_use_no_confidential_project_data_or_full_guide() -> None:
    serialized = json.dumps([topic.__dict__ for topic in ANSWER_SMOKE_TOPICS], ensure_ascii=False).lower()

    assert "secret_project" not in serialized
    forbidden_name = "putki" + "remontti" + "opas"
    assert forbidden_name not in serialized
