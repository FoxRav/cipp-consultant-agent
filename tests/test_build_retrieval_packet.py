from __future__ import annotations

import json

from cipp_contracts.retrieve.build_retrieval_packet import (
    REQUIRED_PACKET_KEYS,
    MemoryRetrievalRepository,
    RetrievalLimits,
    build_retrieval_packet,
    detect_topics,
    render_markdown,
    write_outputs,
)


def fixture_repository() -> MemoryRetrievalRepository:
    return MemoryRetrievalRepository(
        entities=[
            {
                "id": "entity-payment",
                "entity_type": "payment_item",
                "canonical_key": "payment_item:1",
                "canonical_name": "maksuerä 1 hyväksytyn työn jälkeen",
                "project_code": "secret_project_a",
                "source_table": "finance.payment_schedule_items",
                "source_id": "source-payment",
            },
            {
                "id": "entity-boundary",
                "entity_type": "boundary",
                "canonical_key": "boundary:1",
                "canonical_name": "JV pohjaviemäri ja tonttilinja",
                "project_code": "secret_project_b",
                "source_table": "domain.contract_boundaries",
                "source_id": "source-boundary",
            },
        ],
        relations=[
            {
                "id": "relation-payment-document",
                "relation_type": "SUPPORTED_BY",
                "subject_entity_id": "entity-payment",
                "subject_type": "payment_item",
                "subject_name": "maksuerä 1",
                "object_entity_id": "entity-document",
                "object_type": "document",
                "object_name": "maksueräasiakirja",
                "project_code": "secret_project_a",
                "confidence": 1.0,
            }
        ],
        evidence=[
            {
                "id": "evidence-payment",
                "entity_id": "entity-payment",
                "relation_id": None,
                "source_file_id": "source-file-1",
                "section_id": "section-payment",
                "clause_id": "clause-payment",
                "page_id": "page-payment",
                "source_table": "finance.payment_schedule_items",
                "source_id": "source-payment",
                "evidence_note": "Structured payment schedule row.",
                "confidence": 1.0,
            },
            {
                "id": "evidence-relation",
                "entity_id": None,
                "relation_id": "relation-payment-document",
                "source_file_id": "source-file-1",
                "section_id": "section-payment",
                "clause_id": None,
                "page_id": None,
                "source_table": "kg.derived",
                "evidence_note": "Derived support relation.",
                "confidence": 1.0,
            },
        ],
        sections=[
            {
                "id": "section-payment",
                "project_code": "secret_project_a",
                "document_type": "payment_schedule",
                "source_file_id": "source-file-1",
                "section_key": "1",
                "title": "Maksuerät",
                "body_text": "Payment items are paid after approved work.",
            }
        ],
        clauses=[
            {
                "id": "clause-payment",
                "project_code": "secret_project_a",
                "document_type": "payment_schedule",
                "source_file_id": "source-file-1",
                "clause_key": "1.1",
                "clause_type": "payment",
                "title": "Maksuehto",
                "clause_text": "Maksuerä edellyttää valvojan hyväksyntää.",
            }
        ],
        raw_pages=[
            {
                "id": "page-payment",
                "project_code": "secret_project_a",
                "document_type": "payment_schedule",
                "source_file_id": "source-file-1",
                "page_no": 2,
                "raw_text": "Maksuerätaulukko sivulla 2.",
            }
        ],
    )


def test_payment_question_detects_payment_topic() -> None:
    topics, matches = detect_topics("Mitä maksueristä kannattaa sopia?")

    assert "payment" in topics
    assert "maksuerä" in matches or "maksueristä" not in matches


def test_user_case_parameters_are_stored_in_packet() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Paljonko JV-linjojen sukitus voisi maksaa?",
        user_case={"apartments_count": 30, "jv_verticals_count": 8},
    )

    assert packet["user_case"]["apartments_count"] == 30
    assert packet["user_case"]["jv_verticals_count"] == 8


def test_query_does_not_require_reference_project_code() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert packet["answer_scope"] == "general_cipp_user_case"
    assert packet["reference_usage"]["mode"] == "internal_anonymized_grounding"


def test_kg_entity_returns_from_fixture_by_topic() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert any(entity["entity_type"] == "payment_item" for entity in packet["kg_entities"])


def test_relation_evidence_returns() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert any(item["relation_id"] == "relation-payment-document" for item in packet["evidence"])


def test_section_clause_and_raw_page_text_return_through_evidence() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert packet["sections"][0]["snippet"]
    assert packet["clauses"][0]["snippet"]
    assert packet["raw_pages"][0]["snippet"]


def test_output_does_not_present_reference_project_as_target() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä tapahtui referenssiprojektissa?",
    )

    assert packet["answer_scope"] == "general_cipp_user_case"
    assert any("internal grounding" in warning for warning in packet["warnings"])


def test_reference_usage_is_anonymized() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert packet["reference_usage"]["reference_projects_used"] == ["reference_001"]
    serialized = json.dumps(packet, ensure_ascii=False)
    assert "secret_project_a" not in serialized


def test_no_results_does_not_crash() -> None:
    packet = build_retrieval_packet(
        MemoryRetrievalRepository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert packet["retrieval_status"] == "no_results"
    assert packet["kg_entities"] == []


def test_json_structure_contains_required_top_level_keys() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    assert set(REQUIRED_PACKET_KEYS).issubset(packet.keys())


def test_markdown_output_renders() -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )

    markdown = render_markdown(packet)

    assert "# Retrieval Packet" in markdown
    assert "Reference Usage" in markdown


def test_write_outputs_create_json_and_markdown_without_real_data(tmp_path) -> None:
    packet = build_retrieval_packet(
        fixture_repository(),
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
        limits=RetrievalLimits(entities=5, relations=5, evidence=5, sections=5),
    )
    json_path = tmp_path / "packet.json"
    markdown_path = tmp_path / "packet.md"

    write_outputs(packet, json_path, markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["question"]
    assert markdown_path.read_text(encoding="utf-8").startswith("# Retrieval Packet")
