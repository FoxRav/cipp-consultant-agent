from __future__ import annotations

from cipp_contracts.kg.build_knowledge_graph import MemoryGraphStore, build_graph_from_dataset


def guidance_dataset() -> dict[str, list[dict[str, object]]]:
    return {
        "projects": [],
        "guidance_documents": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "document_code": "fixture_guidance",
                "title": "Fixture guidance",
                "source_type": "expert_guidance",
                "authority_level": "non_binding_guidance",
                "binding_status": "not_binding_law",
                "legal_role": "planning_and_decision_guidance",
                "user_facing_role": "fixture role",
                "source_file_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
        ],
        "guidance_sections": [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "guidance_document_id": "11111111-1111-1111-1111-111111111111",
                "section_number": "1",
                "title": "Planning",
                "page_start": 1,
                "page_end": 1,
                "source_file_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
        ],
        "guidance_items": [
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "guidance_document_id": "11111111-1111-1111-1111-111111111111",
                "section_id": "22222222-2222-2222-2222-222222222222",
                "item_type": "checklist_item",
                "topic_code": "project_governance",
                "process_stage": "project_planning",
                "actor": "board",
                "guidance_summary": "Board should prepare planning inputs.",
                "legal_relevance": "Non-binding expert guidance.",
                "binding_status": "not_binding_law",
                "confidence": 0.9,
                "source_file_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "page_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "metadata": {"legal_references": []},
            }
        ],
    }


def test_kg_builder_creates_guidance_entities_and_evidence() -> None:
    store = MemoryGraphStore()

    stats = build_graph_from_dataset(store, guidance_dataset())

    assert ("guidance_document", "guidance_document:11111111-1111-1111-1111-111111111111") in store.entities
    assert ("guidance_item", "guidance_item:33333333-3333-3333-3333-333333333333") in store.entities
    assert any(rel.relation_type == "HAS_GUIDANCE_ITEM" for rel in store.relations.values())
    assert store.entity_evidence
    assert stats.entities_seen > 0


def test_guidance_entity_metadata_marks_non_binding_source() -> None:
    store = MemoryGraphStore()
    build_graph_from_dataset(store, guidance_dataset())

    item = store.entities[("guidance_item", "guidance_item:33333333-3333-3333-3333-333333333333")]

    assert item.metadata["source_type"] == "expert_guidance"
    assert item.metadata["binding_status"] == "not_binding_law"
