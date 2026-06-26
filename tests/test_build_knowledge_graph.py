from __future__ import annotations

from cipp_contracts.kg.build_knowledge_graph import (
    MemoryGraphStore,
    PostgresGraphStore,
    build_graph_from_dataset,
)


def fixture_dataset() -> dict[str, list[dict[str, object]]]:
    return {
        "projects": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "project_code": "reference_a",
                "project_name_redacted": "Reference A",
                "project_type": "cipp_sukitusurakka",
            }
        ],
        "properties": [
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "project_id": "00000000-0000-0000-0000-000000000001",
                "property_code": "property_001",
                "apartment_count": 10,
                "building_count": 1,
                "floor_area_m2": 500,
            }
        ],
        "contracts": [
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "project_id": "00000000-0000-0000-0000-000000000001",
                "contract_code": "contract_001",
                "contract_type": "construction_contract",
            }
        ],
        "parties": [
            {
                "id": "00000000-0000-0000-0000-000000000004",
                "party_code": "contractor_a",
                "party_type": "contractor",
                "display_name_redacted": "Contractor A",
            }
        ],
        "contract_parties": [
            {
                "id": "00000000-0000-0000-0000-000000000005",
                "contract_id": "00000000-0000-0000-0000-000000000003",
                "party_id": "00000000-0000-0000-0000-000000000004",
                "role": "contractor",
            }
        ],
        "documents": [
            {
                "id": "00000000-0000-0000-0000-000000000006",
                "contract_id": "00000000-0000-0000-0000-000000000003",
                "source_file_id": "00000000-0000-0000-0000-000000000007",
                "document_type": "main_contract",
                "document_title_redacted": "Main Contract",
                "attachment_no": None,
            }
        ],
        "sections": [
            {
                "id": "00000000-0000-0000-0000-000000000008",
                "contract_document_id": "00000000-0000-0000-0000-000000000006",
                "section_key": "1",
                "title": "Scope",
                "page_start": 1,
            }
        ],
        "clauses": [
            {
                "id": "00000000-0000-0000-0000-000000000009",
                "section_id": "00000000-0000-0000-0000-000000000008",
                "clause_key": "1.1",
                "clause_type": "scope",
                "title": "JV scope",
                "source_page": 1,
            }
        ],
        "scope_items": [],
        "boundaries": [],
        "sewer_segments": [],
        "responsibilities": [],
        "technical_requirements": [],
        "quality_requirements": [],
        "quality_inspections": [
            {
                "id": "00000000-0000-0000-0000-000000000011",
                "contract_id": "00000000-0000-0000-0000-000000000003",
                "inspection_text": "video inspection review",
                "source_clause_id": "00000000-0000-0000-0000-000000000009",
            }
        ],
        "quality_defects": [
            {
                "id": "00000000-0000-0000-0000-000000000012",
                "contract_id": "00000000-0000-0000-0000-000000000003",
                "issue_text": "open quality finding",
                "status": "open",
            }
        ],
        "payment_items": [
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "contract_id": "00000000-0000-0000-0000-000000000003",
                "item_no": 1,
                "amount_net": 100,
                "amount_gross": 124,
                "payment_condition": "first milestone",
                "source_document_id": "00000000-0000-0000-0000-000000000006",
            }
        ],
        "unit_prices": [],
        "securities": [],
        "insurances": [],
        "events": [],
        "handover_records": [],
        "observations": [],
    }


def test_builder_creates_core_entities_and_relations() -> None:
    store = MemoryGraphStore()

    build_graph_from_dataset(store, fixture_dataset())

    assert ("project", "project:reference_a") in store.entities
    assert ("contract", "contract:00000000-0000-0000-0000-000000000003") in store.entities
    assert ("document", "document:00000000-0000-0000-0000-000000000006") in store.entities
    assert ("section", "section:00000000-0000-0000-0000-000000000008") in store.entities
    assert (
        ("project", "project:reference_a"),
        "HAS_CONTRACT",
        ("contract", "contract:00000000-0000-0000-0000-000000000003"),
    ) in store.relations
    assert (
        ("project", "project:reference_a"),
        "HAS_DOCUMENT",
        ("document", "document:00000000-0000-0000-0000-000000000006"),
    ) in store.relations
    assert ("inspection", "inspection:00000000-0000-0000-0000-000000000011") in store.entities
    assert ("defect", "defect:00000000-0000-0000-0000-000000000012") in store.entities
    assert (
        ("contract", "contract:00000000-0000-0000-0000-000000000003"),
        "REQUIRES",
        ("inspection", "inspection:00000000-0000-0000-0000-000000000011"),
    ) in store.relations


def test_builder_adds_evidence_for_entities_and_relations() -> None:
    store = MemoryGraphStore()

    build_graph_from_dataset(store, fixture_dataset())

    assert store.entity_evidence
    assert store.relation_evidence
    assert any(evidence.source_table == "core.projects" for _, evidence in store.entity_evidence)
    assert all(evidence.source_table or evidence.source_id for _, evidence in store.relation_evidence)


def test_builder_is_idempotent_in_memory_store() -> None:
    store = MemoryGraphStore()
    data = fixture_dataset()

    build_graph_from_dataset(store, data)
    first_entity_count = len(store.entities)
    first_relation_count = len(store.relations)
    build_graph_from_dataset(store, data)

    assert len(store.entities) == first_entity_count
    assert len(store.relations) == first_relation_count


def test_dry_run_store_does_not_require_database_writes() -> None:
    store = PostgresGraphStore(conn=None, dry_run=True)  # type: ignore[arg-type]

    build_graph_from_dataset(store, fixture_dataset())

    assert store.entity_ids
    assert store.relation_ids


def test_project_code_filter_shape_is_single_project_dataset() -> None:
    store = MemoryGraphStore()
    data = fixture_dataset()
    data["projects"].append(
        {
            "id": "00000000-0000-0000-0000-000000000099",
            "project_code": "reference_b",
            "project_name_redacted": "Reference B",
            "project_type": "cipp_sukitusurakka",
        }
    )
    one_project = {**data, "projects": data["projects"][:1]}

    build_graph_from_dataset(store, one_project)

    assert ("project", "project:reference_a") in store.entities
    assert ("project", "project:reference_b") not in store.entities
