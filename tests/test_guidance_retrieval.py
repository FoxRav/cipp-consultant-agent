from __future__ import annotations

from cipp_contracts.answer.compose_answer import compose_answer
from cipp_contracts.retrieve.build_retrieval_packet import (
    MemoryRetrievalRepository,
    RetrievalLimits,
    build_retrieval_packet,
)


def guidance_repository() -> MemoryRetrievalRepository:
    return MemoryRetrievalRepository(
        entities=[
            {
                "id": "guidance-item-1",
                "entity_type": "guidance_item",
                "canonical_key": "guidance_item:1",
                "canonical_name": "Hallituksen kannattaa aloittaa hankesuunnittelu ajoissa",
                "project_code": None,
                "source_table": "legal.guidance_items",
                "source_id": "33333333-3333-3333-3333-333333333333",
            }
        ],
        relations=[],
        evidence=[
            {
                "id": "evidence-guidance-1",
                "entity_id": "guidance-item-1",
                "relation_id": None,
                "source_file_id": "source-guidance-1",
                "page_id": "page-guidance-1",
                "source_table": "legal.guidance_items",
                "source_id": "33333333-3333-3333-3333-333333333333",
                "evidence_note": "Rules-first non-binding guidance item.",
                "confidence": 0.9,
            }
        ],
        raw_pages=[
            {
                "id": "page-guidance-1",
                "source_file_id": "source-guidance-1",
                "page_no": 4,
                "raw_text": "Hallituksen kannattaa selvittää hankesuunnittelun lähtötiedot ennen urakkatarjouksia.",
                "document_type": "legal_guidance_pipe_renovation",
                "project_code": None,
            }
        ],
    )


def test_retrieval_finds_guidance_for_project_planning_question() -> None:
    packet = build_retrieval_packet(
        guidance_repository(),
        "Milloin taloyhtiön kannattaa aloittaa putkiremontin hankesuunnittelu?",
        limits=RetrievalLimits(entities=5, relations=5, evidence=5, sections=5),
    )

    assert "expert_guidance" in packet["detected_topics"]
    assert packet["retrieval_status"] == "ok"
    assert packet["raw_pages"]


def test_answer_marks_guidance_as_expert_guidance_not_law() -> None:
    packet = build_retrieval_packet(
        guidance_repository(),
        "Mitä amatööritoimijan pitää ymmärtää ennen kuin taloyhtiö pyytää urakkatarjouksia?",
        limits=RetrievalLimits(entities=5, relations=5, evidence=5, sections=5),
    )

    answer = compose_answer(packet)

    assert answer["sources"][0]["source_class"] == "expert_guidance"
    assert any("asiantuntijaoppaaseen" in item for item in answer["uncertainties"])
    assert any("asiantuntijaohjeen perusteella" in point.lower() for point in answer["key_points"])
    assert "laki määrää" not in answer["short_answer"].lower()


def test_answer_keeps_guidance_source_notes_short() -> None:
    packet = build_retrieval_packet(
        guidance_repository(),
        "Mitä amatööritoimijan pitää ymmärtää ennen kuin taloyhtiö pyytää urakkatarjouksia?",
        limits=RetrievalLimits(entities=5, relations=5, evidence=5, sections=5),
    )
    packet["raw_pages"][0]["snippet"] = "Asiantuntijaohje. " + ("Tarkistuslistan kohta. " * 40)

    answer = compose_answer(packet)

    assert len(answer["source_based_notes"][0]) < 420
