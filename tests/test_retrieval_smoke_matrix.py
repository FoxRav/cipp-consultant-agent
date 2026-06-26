from __future__ import annotations

import json

from cipp_contracts.retrieve.report_retrieval_smoke_matrix import (
    ALLOWED_TOPIC_STATUSES,
    SMOKE_TOPICS,
    SmokeTopic,
    build_smoke_matrix,
    check_anonymization,
    render_markdown,
    write_report,
)


def packet(
    status: str = "ok",
    coverage: str = "ok",
    text_context_count: int = 3,
    missing_text_context_count: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "question": "fixture question",
        "answer_scope": "general_cipp_user_case",
        "user_case": {},
        "retrieval_status": status,
        "evidence_coverage_status": coverage,
        "text_context_count": text_context_count,
        "missing_text_context_count": missing_text_context_count,
        "detected_topics": ["fixture_topic"],
        "missing_user_case_fields": [],
        "kg_entities": [
            {
                "id": "entity-1",
                "entity_type": "scope_item",
                "name": "fixture scope",
                "reference_label": "reference_001",
                "text_context_status": "direct_section",
            }
        ],
        "kg_relations": [
            {
                "id": "relation-1",
                "relation_type": "DEFINES",
                "reference_label": "reference_001",
                "subject": {"type": "contract", "name": "fixture contract"},
                "object": {"type": "scope_item", "name": "fixture scope"},
                "text_context_status": "direct_section",
            }
        ],
        "evidence": [
            {
                "id": "evidence-1",
                "source_table": "domain.scope_items",
                "evidence_note": "Fixture evidence.",
                "confidence": 1.0,
                "text_context_status": "direct_section",
            }
        ],
        "sections": [
            {
                "id": "section-1",
                "title": "Fixture section",
                "snippet": "Fixture text context.",
            }
        ],
        "clauses": [],
        "raw_pages": [],
        "reference_usage": {
            "mode": "internal_anonymized_grounding",
            "reference_projects_used": ["reference_001"],
        },
        "warnings": warnings or [],
    }


def test_smoke_matrix_contains_10_standard_topics() -> None:
    assert len(SMOKE_TOPICS) == 10
    assert {topic.topic_code for topic in SMOKE_TOPICS} == {
        "payment",
        "wastewater_scope",
        "stormwater_scope",
        "boundaries",
        "video_inspection",
        "handover",
        "warranty",
        "security_insurance",
        "unit_prices_change_work",
        "defects_claims",
    }


def test_each_standard_topic_has_code_and_question() -> None:
    for topic in SMOKE_TOPICS:
        assert topic.topic_code
        assert topic.question


def test_topic_status_is_pass_partial_or_fail() -> None:
    statuses = {
        row["topic_status"]
        for row in build_smoke_matrix(lambda _question: packet(), topics=SMOKE_TOPICS).get("topics", [])
    }

    assert statuses <= ALLOWED_TOPIC_STATUSES


def test_summary_counts_passed_partial_failed() -> None:
    packets = iter(
        [
            packet(),
            packet(status="partial", coverage="partial", missing_text_context_count=1),
            packet(status="no_results", coverage="no_text_context", text_context_count=0),
        ]
    )
    report = build_smoke_matrix(
        lambda _question: next(packets),
        topics=(
            SmokeTopic("payment", "payment?"),
            SmokeTopic("wastewater_scope", "jv?"),
            SmokeTopic("boundaries", "boundary?"),
        ),
    )

    assert report["summary"]["passed"] == 1
    assert report["summary"]["partial"] == 1
    assert report["summary"]["failed"] == 1


def test_release_candidate_false_if_blocking_topic_fails() -> None:
    report = build_smoke_matrix(
        lambda question: packet(status="no_results", coverage="no_text_context", text_context_count=0)
        if "payment" in question
        else packet(),
        topics=(
            SmokeTopic("payment", "payment"),
            SmokeTopic("wastewater_scope", "jv"),
            SmokeTopic("boundaries", "boundary"),
        ),
    )

    assert report["summary"]["release_candidate"] is False
    assert "payment" in report["summary"]["blocking_topics"]


def test_release_candidate_true_when_required_topics_pass_or_allowed_partial() -> None:
    def builder(question: str) -> dict[str, object]:
        if question in {"video", "handover", "warranty"}:
            return packet(status="partial", coverage="partial", missing_text_context_count=1)
        return packet()

    report = build_smoke_matrix(
        builder,
        topics=(
            SmokeTopic("payment", "payment"),
            SmokeTopic("wastewater_scope", "jv"),
            SmokeTopic("boundaries", "boundary"),
            SmokeTopic("video_inspection", "video"),
            SmokeTopic("handover", "handover"),
            SmokeTopic("warranty", "warranty"),
        ),
    )

    assert report["summary"]["release_candidate"] is True


def test_markdown_output_renders() -> None:
    report = build_smoke_matrix(lambda _question: packet(), topics=(SmokeTopic("payment", "payment"),))

    markdown = render_markdown(report)

    assert "# Retrieval Smoke Matrix" in markdown
    assert "Release candidate" in markdown


def test_json_output_writes(tmp_path) -> None:
    report = build_smoke_matrix(lambda _question: packet(), topics=(SmokeTopic("payment", "payment"),))
    output = tmp_path / "smoke.json"
    output_md = tmp_path / "smoke.md"

    write_report(report, output, output_md)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "retrieval_smoke_matrix"
    assert output_md.read_text(encoding="utf-8").startswith("# Retrieval Smoke Matrix")


def test_anonymization_check_detects_project_name_and_windows_path() -> None:
    status, warnings = check_anonymization("Leaked path F:\\secret and AOY Salainen")

    assert status == "failed"
    assert warnings


def test_tests_use_no_real_confidential_data() -> None:
    serialized = json.dumps([topic.__dict__ for topic in SMOKE_TOPICS], ensure_ascii=False).lower()

    assert "reference_" not in serialized
    assert "secret_project" not in serialized
