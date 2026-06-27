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


def test_cost_question_detects_cost_estimate_topic_without_payment_topic() -> None:
    topics, matches = detect_topics("Paljonko yllä kuvatun taloyhtiön urakka maksaa?")

    assert "cost_estimate" in topics
    assert "payment" not in topics
    assert any(match in matches for match in ("paljonko yllä kuvatun taloyhtiön urakka maksaa", "hinta"))


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


def test_known_reference_markers_are_sanitized_from_text_context() -> None:
    repository = fixture_repository()
    repository.sections[0]["body_text"] = "Referenssikoivu vastaanotto todettiin valmiiksi."
    repository.raw_pages[0]["raw_text"] = "Mallihovi loppukuvaus ja Esimerkkitalo vakuudet."

    packet = build_retrieval_packet(
        repository,
        "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    )
    markdown = render_markdown(packet).lower()

    assert "referenssikoivu" not in markdown
    assert "mallihovi" not in markdown
    assert "esimerkkitalo" not in markdown
    assert "[reference redacted]" in markdown


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


def sewer_repository() -> MemoryRetrievalRepository:
    return MemoryRetrievalRepository(
        entities=[
            {
                "id": "entity-scope",
                "entity_type": "scope_item",
                "canonical_key": "scope_item:jv",
                "canonical_name": "JV pystylinjat ja pohjaviemäri",
                "project_code": "secret_project_jv",
                "source_table": "domain.scope_items",
                "source_id": "source-scope",
            },
            {
                "id": "entity-segment",
                "entity_type": "sewer_segment",
                "canonical_key": "sewer_segment:jv-bottom",
                "canonical_name": "pohjaviemäri",
                "project_code": "secret_project_jv",
                "source_table": "domain.sewer_segments",
                "source_id": "source-segment",
            },
        ],
        relations=[
            {
                "id": "relation-scope-segment",
                "relation_type": "AFFECTS",
                "subject_entity_id": "entity-scope",
                "subject_type": "scope_item",
                "subject_name": "JV pystylinjat",
                "object_entity_id": "entity-segment",
                "object_type": "sewer_segment",
                "object_name": "pohjaviemäri",
                "project_code": "secret_project_jv",
                "confidence": 1.0,
            }
        ],
        evidence=[
            {
                "id": "evidence-scope",
                "entity_id": "entity-scope",
                "relation_id": None,
                "source_file_id": None,
                "section_id": "section-jv",
                "clause_id": "clause-jv",
                "page_id": "page-jv",
                "source_table": "domain.scope_items",
                "source_id": "source-scope",
                "evidence_note": "Structured JV scope row.",
                "confidence": 1.0,
            },
            {
                "id": "evidence-relation-jv",
                "entity_id": None,
                "relation_id": "relation-scope-segment",
                "source_file_id": None,
                "section_id": "section-jv",
                "clause_id": None,
                "page_id": None,
                "source_table": "domain.sewer_segments",
                "source_id": "source-segment",
                "evidence_note": "Scope affects sewer segment.",
                "confidence": 1.0,
            },
        ],
        sections=[
            {
                "id": "section-jv",
                "project_code": "secret_project_jv",
                "document_type": "rfq",
                "section_key": "2",
                "title": "JV-laajuus",
                "body_text": "Urakka sisältää JV-pystylinjat, pohjaviemärin ja tonttiviemärin rajaukset.",
            }
        ],
        clauses=[
            {
                "id": "clause-jv",
                "project_code": "secret_project_jv",
                "document_type": "rfq",
                "clause_key": "2.1",
                "clause_type": "scope",
                "title": "JV scope",
                "clause_text": "Pohjaviemäri ja tonttilinja kuuluvat sovittuun urakkarajaan.",
            }
        ],
        raw_pages=[
            {
                "id": "page-jv",
                "project_code": "secret_project_jv",
                "document_type": "rfq",
                "source_file_id": "source-file-jv",
                "page_no": 4,
                "raw_text": "JV pystylinjat ja pohjaviemäri kuvataan tarjouspyynnössä.",
            }
        ],
    )


def test_jv_question_detects_sewer_scope_boundary_topic() -> None:
    topics, matches = detect_topics("Mitä pitää huomioida JV-pystylinjoissa ja pohjaviemärissä?")

    assert "wastewater_sewer" in topics
    assert {"jv", "pystylinja", "pohjaviemäri"}.intersection(matches)


def test_sewer_scope_boundary_entity_and_relation_evidence_return() -> None:
    packet = build_retrieval_packet(
        sewer_repository(),
        "Mitä pitää huomioida JV-pystylinjojen ja pohjaviemärin sukituksessa?",
    )

    assert any(entity["entity_type"] == "scope_item" for entity in packet["kg_entities"])
    assert any(relation["relation_type"] == "AFFECTS" for relation in packet["kg_relations"])
    assert any(item["source_table"] == "domain.scope_items" for item in packet["evidence"])


def test_direct_clause_section_and_page_statuses_are_reported() -> None:
    packet = build_retrieval_packet(
        sewer_repository(),
        "Mitä pitää huomioida JV-pystylinjojen ja pohjaviemärin sukituksessa?",
    )

    assert any(item["text_context_status"] == "direct_clause" for item in packet["evidence"])
    assert any(section["text_context_status"] == "direct_section" for section in packet["sections"])
    assert any(page["text_context_status"] == "direct_page" for page in packet["raw_pages"])


def test_source_file_fallback_fetches_raw_page_snippet() -> None:
    repo = MemoryRetrievalRepository(
        entities=[
            {
                "id": "entity-source-file",
                "entity_type": "scope_item",
                "canonical_name": "JV tonttiviemäri",
                "project_code": "secret_source_file_project",
                "source_table": "domain.scope_items",
                "source_id": "source-1",
            }
        ],
        evidence=[
            {
                "id": "evidence-source-file",
                "entity_id": "entity-source-file",
                "source_file_id": "source-file-jv",
                "source_table": "domain.scope_items",
            }
        ],
        source_file_pages=[
            {
                "id": "page-from-source-file",
                "source_file_id": "source-file-jv",
                "project_code": "secret_source_file_project",
                "document_type": "rfq",
                "page_no": 1,
                "raw_text": "JV tonttiviemäri ja pohjaviemäri kuvataan tällä sivulla.",
            }
        ],
    )

    packet = build_retrieval_packet(repo, "Mitä JV tonttiviemäristä pitää huomioida?")

    assert packet["raw_pages"][0]["text_context_status"] == "source_file_page"
    assert packet["evidence"][0]["text_context_status"] == "source_file_page"


def test_entity_source_fallback_marks_domain_context() -> None:
    repo = MemoryRetrievalRepository(
        entities=[
            {
                "id": "entity-domain",
                "entity_type": "boundary",
                "canonical_name": "JV urakkaraja",
                "project_code": "secret_domain_project",
                "source_table": "domain.contract_boundaries",
                "source_id": "boundary-1",
            }
        ],
        evidence=[
            {
                "id": "evidence-domain",
                "entity_id": "entity-domain",
                "source_table": "domain.contract_boundaries",
                "source_id": "boundary-1",
            }
        ],
        topic_sections=[
            {
                "id": "topic-section-domain",
                "project_code": "secret_domain_project",
                "document_type": "rfq",
                "section_key": "3",
                "title": "Urakkaraja",
                "body_text": "JV urakkaraja määrittää pohjaviemärin ja tonttilinjan vastuut.",
            }
        ],
    )

    packet = build_retrieval_packet(repo, "Mitä JV urakkarajassa pitää huomioida?")

    assert packet["evidence"][0]["text_context_status"] == "entity_source_fallback"
    assert packet["evidence_coverage_status"] == "ok"


def test_topic_text_fallback_is_weak_lower_confidence_context() -> None:
    repo = MemoryRetrievalRepository(
        entities=[
            {
                "id": "entity-topic",
                "entity_type": "document",
                "canonical_name": "JV dokumentti",
                "project_code": "secret_topic_project",
                "source_table": "core.contract_documents",
            }
        ],
        evidence=[
            {
                "id": "evidence-topic",
                "entity_id": "entity-topic",
                "source_table": "kg.derived",
            }
        ],
        topic_sections=[
            {
                "id": "topic-section",
                "project_code": "secret_topic_project",
                "document_type": "rfq",
                "section_key": "4",
                "title": "JV",
                "body_text": "JV pohjaviemäri mainitaan projektin tarjouspyynnössä.",
            }
        ],
    )

    packet = build_retrieval_packet(repo, "Mitä JV pohjaviemäristä pitää huomioida?")

    assert packet["evidence"][0]["text_context_status"] == "topic_text_fallback"
    assert packet["evidence_coverage_status"] == "weak"


def test_jv_sample_is_ok_when_text_context_exists() -> None:
    packet = build_retrieval_packet(
        sewer_repository(),
        "Mitä pitää huomioida JV-pystylinjojen ja pohjaviemärin sukituksessa?",
    )

    assert packet["retrieval_status"] == "ok"
    assert packet["evidence_coverage_status"] == "ok"


def test_no_text_context_status_is_controlled() -> None:
    repo = MemoryRetrievalRepository(
        entities=[
            {
                "id": "entity-no-text",
                "entity_type": "scope_item",
                "canonical_name": "JV laajuus",
                "project_code": "secret_no_text",
                "source_table": "domain.scope_items",
            }
        ],
        evidence=[{"id": "evidence-no-text", "entity_id": "entity-no-text"}],
    )

    packet = build_retrieval_packet(repo, "Mitä JV laajuudesta pitää huomioida?")

    assert packet["evidence_coverage_status"] == "no_text_context"
    assert packet["retrieval_status"] == "partial"


def test_markdown_output_includes_coverage_and_stays_anonymized() -> None:
    packet = build_retrieval_packet(
        sewer_repository(),
        "Mitä pitää huomioida JV-pystylinjojen ja pohjaviemärin sukituksessa?",
    )
    markdown = render_markdown(packet)

    assert "Evidence Coverage" in markdown
    assert "secret_project_jv" not in markdown
    assert "reference_001" in markdown
