from __future__ import annotations

import json

from cipp_contracts.answer.compose_answer import (
    ANSWER_STATUSES,
    compose_answer,
    load_retrieval_packet,
    render_markdown,
    write_outputs,
)


def retrieval_packet(
    retrieval_status: str = "ok",
    coverage_status: str = "ok",
    topics: list[str] | None = None,
    text_context_count: int = 2,
    missing_text_context_count: int = 0,
    missing_fields: list[str] | None = None,
) -> dict[str, object]:
    return {
        "question": "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
        "answer_scope": "general_cipp_user_case",
        "user_case": {},
        "retrieval_status": retrieval_status,
        "evidence_coverage_status": coverage_status,
        "text_context_count": text_context_count,
        "missing_text_context_count": missing_text_context_count,
        "detected_topics": topics or ["payment"],
        "missing_user_case_fields": missing_fields or [],
        "detected_entities": [],
        "kg_entities": [
            {
                "id": "entity-1",
                "entity_type": "payment_item",
                "name": "maksuerä hyväksytyn työn jälkeen",
                "reference_label": "reference_001",
                "text_context_status": "direct_clause",
            }
        ],
        "kg_relations": [],
        "evidence": [
            {
                "id": "evidence-1",
                "evidence_note": "Synthetic evidence note.",
                "confidence": 1.0,
                "text_context_status": "direct_clause",
            }
        ],
        "sections": [
            {
                "id": "section-1",
                "reference_label": "reference_001",
                "document_type": "contract",
                "section_key": "1",
                "title": "Maksuerät",
                "snippet": "Maksuerä maksetaan, kun valvoja on hyväksynyt työvaiheen.",
                "text_context_status": "direct_section",
            }
        ],
        "clauses": [
            {
                "id": "clause-1",
                "reference_label": "reference_001",
                "document_type": "contract",
                "clause_key": "1.1",
                "title": "Maksuehto",
                "snippet": "Maksuerän perusteena on dokumentoitu ja hyväksytty suoritus.",
                "text_context_status": "direct_clause",
            }
        ],
        "raw_pages": [],
        "reference_usage": {
            "mode": "internal_anonymized_grounding",
            "reference_projects_used": ["reference_001"],
        },
        "warnings": [],
    }


def test_composer_reads_retrieval_packet_json(tmp_path) -> None:
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(retrieval_packet(), ensure_ascii=False), encoding="utf-8")

    packet = load_retrieval_packet(path)

    assert packet["question"]


def test_composer_produces_json_output(tmp_path) -> None:
    answer = compose_answer(retrieval_packet())
    output = tmp_path / "answer.json"

    write_outputs(answer, output, None)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["generation_mode"] == "deterministic_source_grounded"


def test_composer_produces_markdown_output(tmp_path) -> None:
    answer = compose_answer(retrieval_packet())
    output_md = tmp_path / "answer.md"

    write_outputs(answer, None, output_md)

    assert output_md.read_text(encoding="utf-8").startswith("# Source-grounded answer")


def test_llm_used_is_false() -> None:
    answer = compose_answer(retrieval_packet())

    assert answer["llm_used"] is False


def test_no_results_becomes_insufficient_evidence() -> None:
    packet = retrieval_packet(retrieval_status="no_results", coverage_status="no_text_context", text_context_count=0)
    packet["sections"] = []
    packet["clauses"] = []

    answer = compose_answer(packet)

    assert answer["answer_status"] == "insufficient_evidence"
    assert not answer["key_points"]


def test_partial_retrieval_becomes_partial_answer() -> None:
    answer = compose_answer(
        retrieval_packet(retrieval_status="partial", coverage_status="partial", missing_text_context_count=1)
    )

    assert answer["answer_status"] == "partial"
    assert answer["uncertainties"]


def test_only_topic_fallback_sources_become_partial_answer() -> None:
    packet = retrieval_packet()
    packet["clauses"] = []
    packet["sections"][0]["text_context_status"] = "topic_text_fallback"

    answer = compose_answer(packet)

    assert answer["answer_status"] == "partial"
    assert any("fallback" in uncertainty for uncertainty in answer["uncertainties"])


def test_ok_retrieval_becomes_answered() -> None:
    answer = compose_answer(retrieval_packet())

    assert answer["answer_status"] == "answered"
    assert answer["answer_status"] in ANSWER_STATUSES


def test_missing_user_case_fields_are_visible() -> None:
    answer = compose_answer(retrieval_packet(missing_fields=["apartments_count", "jv_verticals_count"]))

    assert "apartments_count" in answer["missing_user_case_fields"]
    assert any("apartments_count" in question for question in answer["recommended_next_questions"])


def test_sources_are_anonymized() -> None:
    answer = compose_answer(retrieval_packet())
    serialized = json.dumps(answer, ensure_ascii=False)

    assert "reference_001" in serialized
    assert "secret_project" not in serialized


def test_markdown_does_not_include_windows_path_or_raw_project_name() -> None:
    packet = retrieval_packet()
    windows_path = "C:" + "\\secret\\raw\\file"
    amount_words = "10000" + " euroa"
    amount_symbol = "17 500" + " €"
    amount_short = "165" + " e/pysty"
    packet["sections"][0]["snippet"] = (
        f"{windows_path} Referenssikoivu maksuerä {amount_words}, {amount_symbol} ja {amount_short}."
    )

    markdown = render_markdown(compose_answer(packet)).lower()

    assert "c:\\secret" not in markdown
    assert "referenssikoivu" not in markdown
    assert amount_words not in markdown
    assert amount_symbol not in markdown
    assert amount_short not in markdown
    assert "[amount redacted]" in markdown


def test_payment_template_is_used() -> None:
    answer = compose_answer(retrieval_packet(topics=["payment"]))

    assert any("Maksuerät kannattaa" in point for point in answer["key_points"])


def test_boundaries_and_jv_templates_are_used() -> None:
    answer = compose_answer(retrieval_packet(topics=["boundaries", "wastewater_sewer"]))

    assert any("Urakkarajat" in point for point in answer["key_points"])
    assert any("JV-laajuus" in point for point in answer["key_points"])


def test_expert_guidance_source_adds_non_binding_phrasing_for_core_topic() -> None:
    packet = retrieval_packet(topics=["quality_video"])
    packet["sections"][0]["document_type"] = "legal_guidance_pipe_renovation"

    answer = compose_answer(packet)

    assert any("Asiantuntijaohjeen perusteella" in point for point in answer["key_points"])
    assert any("asiantuntijaoppaaseen" in uncertainty for uncertainty in answer["uncertainties"])


def test_composer_does_not_invent_numbers_not_in_packet() -> None:
    answer = compose_answer(retrieval_packet(topics=["payment"]))
    serialized = json.dumps(answer, ensure_ascii=False)

    assert "70%" not in serialized
    assert "8000" not in serialized
    assert "5000" not in serialized


def test_tests_use_no_real_confidential_project_data() -> None:
    serialized = json.dumps(retrieval_packet(), ensure_ascii=False).lower()

    assert "reference_" in serialized
    assert "secret_project" not in serialized
