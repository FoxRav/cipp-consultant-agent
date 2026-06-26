from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url
from cipp_contracts.retrieve.build_retrieval_packet import (
    PostgresRetrievalRepository,
    RetrievalLimits,
    build_retrieval_packet,
    render_markdown as render_packet_markdown,
)


REPORT_TYPE = "retrieval_smoke_matrix"
ALLOWED_TOPIC_STATUSES = {"pass", "partial", "fail"}
CORE_REQUIRED_PASS = {"payment", "wastewater_scope", "boundaries"}
CORE_REQUIRED_AT_LEAST_PARTIAL = {"video_inspection", "handover", "warranty"}
LEAK_PATTERNS = (
    r"F:\\",
    r"[A-Z]:\\",
    r"\.pdf\b",
    r"\.docx?\b",
    r"\.xlsx?\b",
    r"\.dwg\b",
    r"\.txt\b",
    r"data\\raw",
    r"data/raw",
    r"\b(?:as\s+oy|aoy)\s+[a-zåäö]",
)
CASE_SENSITIVE_LEAK_PATTERNS = (
    r"\b[A-ZÅÄÖ][A-Za-zÅÄÖåäö-]*(?:koivu|hovi|talo)\b",
)


@dataclass(frozen=True)
class SmokeTopic:
    topic_code: str
    question: str


SMOKE_TOPICS = (
    SmokeTopic("payment", "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?"),
    SmokeTopic(
        "wastewater_scope",
        "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?",
    ),
    SmokeTopic(
        "stormwater_scope",
        "Mitä pitää huomioida sadevesilinjojen ja kattokaivojen sukituksessa?",
    ),
    SmokeTopic(
        "boundaries",
        "Mitä urakkarajoissa pitää huomioida ja miten määritellään mikä kuuluu urakkaan?",
    ),
    SmokeTopic(
        "video_inspection",
        "Mitä videotarkastuksesta ja loppukuvauksesta pitää vaatia CIPP-urakassa?",
    ),
    SmokeTopic(
        "handover",
        "Mitä vastaanotossa pitää tarkistaa ennen CIPP-urakan hyväksymistä?",
    ),
    SmokeTopic("warranty", "Miten takuuasiat kannattaa kirjata CIPP-sukitusurakassa?"),
    SmokeTopic(
        "security_insurance",
        "Mitä vakuuksia ja vakuutuksia CIPP-urakassa pitää huomioida?",
    ),
    SmokeTopic(
        "unit_prices_change_work",
        "Miten lisätyöt ja yksikköhinnat kannattaa määritellä sukitusurakassa?",
    ),
    SmokeTopic(
        "defects_claims",
        "Miten puutteet, virheet ja reklamaatiot pitää dokumentoida CIPP-urakassa?",
    ),
)
GUIDANCE_SMOKE_TOPICS = (
    SmokeTopic("guidance_project_planning", "Milloin taloyhtiön kannattaa aloittaa putkiremontin hankesuunnittelu?"),
    SmokeTopic("guidance_board_checks", "Mitä hallituksen pitää selvittää ennen putkiremontin suunnittelua?"),
    SmokeTopic("guidance_shareholder_questions", "Mitä kysymyksiä osakkaiden kannattaa esittää ennen sukituspäätöstä?"),
    SmokeTopic("guidance_condition_survey", "Milloin kuntotutkimus tai koejyrsintä tarvitaan?"),
    SmokeTopic("guidance_coating_risks", "Mitä riskejä pinnoitukseen liittyy?"),
    SmokeTopic("guidance_cipp_conditions", "Mihin sukitus soveltuu ja mitä pitää varmistaa ennen työn tilaamista?"),
    SmokeTopic("guidance_housing_company_decision", "Mitä yhtiökokouksen pitää hyväksyä ennen suunnittelun jatkamista?"),
    SmokeTopic("guidance_handover_warranty", "Mitä vastaanotossa ja takuuajassa pitää huomioida?"),
    SmokeTopic("guidance_permit_obligations", "Milloin rakennuslupa tai muu viranomaisvelvoite voi tulla mukaan?"),
    SmokeTopic(
        "guidance_amateur_procurement",
        "Mitä amatööritoimijan pitää ymmärtää ennen kuin taloyhtiö pyytää urakkatarjouksia?",
    ),
)


class PacketBuilder(Protocol):
    def __call__(self, question: str) -> dict[str, Any]: ...


def build_smoke_matrix(
    packet_builder: PacketBuilder,
    topics: tuple[SmokeTopic, ...] = SMOKE_TOPICS,
    stop_on_fail: bool = False,
    include_debug: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for topic in topics:
        try:
            packet = packet_builder(topic.question)
            markdown = render_packet_markdown(packet)
            row = evaluate_packet(topic, packet, markdown, include_debug=include_debug)
        except Exception as exc:  # pragma: no cover - exercised through CLI resilience.
            row = failed_topic(topic, str(exc), include_debug=include_debug)
        rows.append(row)
        if stop_on_fail and row["topic_status"] == "fail":
            break
    return {
        "report_type": REPORT_TYPE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize(rows),
        "topics": rows,
    }


def evaluate_packet(
    topic: SmokeTopic,
    packet: dict[str, Any],
    markdown: str,
    include_debug: bool = False,
) -> dict[str, Any]:
    warnings = list(packet.get("warnings") or [])
    failure_reasons: list[str] = []
    anonymization_status, anonymization_warnings = check_anonymization(markdown)
    warnings.extend(anonymization_warnings)

    retrieval_status = packet.get("retrieval_status")
    evidence_coverage_status = packet.get("evidence_coverage_status")
    text_context_count = int(packet.get("text_context_count") or 0)
    missing_text_context_count = int(packet.get("missing_text_context_count") or 0)

    if retrieval_status == "no_results":
        failure_reasons.append("retrieval returned no results")
    if evidence_coverage_status == "no_text_context":
        failure_reasons.append("no text context found")
    if text_context_count == 0:
        failure_reasons.append("text context count is zero")
    if anonymization_status == "failed":
        failure_reasons.append("anonymization check failed")

    if failure_reasons:
        topic_status = "fail"
    elif (
        retrieval_status == "ok"
        and evidence_coverage_status == "ok"
        and text_context_count > 0
        and missing_text_context_count == 0
        and anonymization_status == "ok"
    ):
        topic_status = "pass"
    else:
        topic_status = "partial"
        if retrieval_status != "ok":
            failure_reasons.append(f"retrieval status is {retrieval_status}")
        if evidence_coverage_status != "ok":
            failure_reasons.append(f"evidence coverage is {evidence_coverage_status}")
        if missing_text_context_count:
            failure_reasons.append(f"missing text contexts: {missing_text_context_count}")
        if not failure_reasons:
            failure_reasons.append("retrieval is usable but not fully passing")

    row = {
        "topic_code": topic.topic_code,
        "question": topic.question,
        "topic_status": topic_status,
        "retrieval_status": retrieval_status,
        "evidence_coverage_status": evidence_coverage_status,
        "text_context_count": text_context_count,
        "missing_text_context_count": missing_text_context_count,
        "detected_topics": packet.get("detected_topics") or [],
        "kg_entities_count": len(packet.get("kg_entities") or []),
        "kg_relations_count": len(packet.get("kg_relations") or []),
        "evidence_count": len(packet.get("evidence") or []),
        "sections_count": len(packet.get("sections") or []),
        "clauses_count": len(packet.get("clauses") or []),
        "raw_pages_count": len(packet.get("raw_pages") or []),
        "reference_usage_count": len((packet.get("reference_usage") or {}).get("reference_projects_used") or []),
        "warnings": warnings,
        "failure_reasons": failure_reasons,
        "anonymization_status": anonymization_status,
    }
    if include_debug:
        row["packet_debug"] = packet
    return row


def failed_topic(topic: SmokeTopic, error: str, include_debug: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {
        "topic_code": topic.topic_code,
        "question": topic.question,
        "topic_status": "fail",
        "retrieval_status": "no_results",
        "evidence_coverage_status": "no_text_context",
        "text_context_count": 0,
        "missing_text_context_count": 0,
        "detected_topics": [],
        "kg_entities_count": 0,
        "kg_relations_count": 0,
        "evidence_count": 0,
        "sections_count": 0,
        "clauses_count": 0,
        "raw_pages_count": 0,
        "reference_usage_count": 0,
        "warnings": [f"Smoke topic crashed: {error}"],
        "failure_reasons": ["command crashed"],
        "anonymization_status": "failed",
    }
    if include_debug:
        row["error_debug"] = error
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for row in rows if row["topic_status"] == "pass")
    partial = sum(1 for row in rows if row["topic_status"] == "partial")
    failed = sum(1 for row in rows if row["topic_status"] == "fail")
    blocking = blocking_topics(rows)
    return {
        "total_topics": len(rows),
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "release_candidate": not blocking,
        "blocking_topics": blocking,
    }


def blocking_topics(rows: list[dict[str, Any]]) -> list[str]:
    by_code = {row["topic_code"]: row for row in rows}
    blocking: list[str] = []
    for code in CORE_REQUIRED_PASS:
        row = by_code.get(code)
        if not row or row["topic_status"] != "pass":
            blocking.append(code)
    for code in CORE_REQUIRED_AT_LEAST_PARTIAL:
        row = by_code.get(code)
        if not row or row["topic_status"] == "fail":
            blocking.append(code)
    for row in rows:
        if row["topic_status"] == "fail" and row["topic_code"] not in blocking:
            blocking.append(row["topic_code"])
        if row["anonymization_status"] == "failed" and row["topic_code"] not in blocking:
            blocking.append(row["topic_code"])
    return sorted(blocking)


def check_anonymization(markdown: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    for pattern in LEAK_PATTERNS:
        if re.search(pattern, markdown, flags=re.IGNORECASE):
            warnings.append(f"Potential leak pattern matched: {pattern}")
    for pattern in CASE_SENSITIVE_LEAK_PATTERNS:
        if re.search(pattern, markdown):
            warnings.append(f"Potential leak pattern matched: {pattern}")
    return ("failed" if warnings else "ok", warnings)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Retrieval Smoke Matrix",
        "",
        "## Summary",
        "",
        f"- Total topics: {summary['total_topics']}",
        f"- Passed: {summary['passed']}",
        f"- Partial: {summary['partial']}",
        f"- Failed: {summary['failed']}",
        f"- Release candidate: `{str(summary['release_candidate']).lower()}`",
        "",
        "## Topic Table",
        "",
        "| Topic | Status | Retrieval | Evidence | Text | Missing | Anonymization |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in report["topics"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row["topic_code"]),
                    _md(row["topic_status"]),
                    _md(row["retrieval_status"]),
                    _md(row["evidence_coverage_status"]),
                    str(row["text_context_count"]),
                    str(row["missing_text_context_count"]),
                    _md(row["anonymization_status"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blocking Topics", "", _list_or_none(summary["blocking_topics"]), ""])
    lines.extend(["## Per-Topic Details", ""])
    for row in report["topics"]:
        lines.extend(
            [
                f"### {_md(row['topic_code'])}",
                "",
                f"- Question: {_md(row['question'])}",
                f"- Topic status: `{_md(row['topic_status'])}`",
                f"- Detected topics: {_md(', '.join(row['detected_topics']))}",
                f"- KG entities: {row['kg_entities_count']}",
                f"- KG relations: {row['kg_relations_count']}",
                f"- Evidence rows: {row['evidence_count']}",
                f"- Sections/clauses/raw pages: {row['sections_count']}/{row['clauses_count']}/{row['raw_pages_count']}",
                f"- Reference usage count: {row['reference_usage_count']}",
                "",
                "Warnings:",
                _list_or_none(row["warnings"]),
                "",
                "Failure / partial reasons:",
                _list_or_none(row["failure_reasons"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Anonymization Notes",
            "",
            "Markdown smoke checks are pattern-based. They reject known real project markers, Windows paths, raw file paths, and document-like filenames.",
            "",
            "This report tests retrieval readiness only. It is not an agent answer and does not call an LLM.",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: Path | None, output_md: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(report) + "\n", encoding="utf-8")


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _list_or_none(values: list[Any]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {_md(value)}" for value in values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--stop-on-fail", action="store_true")
    parser.add_argument("--include-debug", action="store_true")
    parser.add_argument("--include-guidance-topics", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    with psycopg.connect(database_url(args.db, args.env), row_factory=dict_row) as conn:
        repository = PostgresRetrievalRepository(conn)
        limits = RetrievalLimits()

        def packet_builder(question: str) -> dict[str, Any]:
            return build_retrieval_packet(repository, question, limits=limits)

        topics = SMOKE_TOPICS + GUIDANCE_SMOKE_TOPICS if args.include_guidance_topics else SMOKE_TOPICS
        report = build_smoke_matrix(
            packet_builder,
            topics=topics,
            stop_on_fail=args.stop_on_fail,
            include_debug=args.include_debug,
        )
    if not args.dry_run:
        write_report(report, args.output, args.output_md)
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
