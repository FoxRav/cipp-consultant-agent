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

from cipp_contracts.answer.compose_answer import compose_answer, render_markdown
from cipp_contracts.config import database_url
from cipp_contracts.retrieve.build_retrieval_packet import (
    PostgresRetrievalRepository,
    RetrievalLimits,
    build_retrieval_packet,
)


REPORT_TYPE = "answer_smoke_matrix"
ALLOWED_TOPIC_STATUSES = {"pass", "partial", "fail"}
FAILED_STATUSES = {"failed"}
WARNING_STATUSES = {"warning", "failed"}
BINDING_LAW_PATTERNS = (
    r"\blaki määrää\b",
    r"\bon lain mukaan pakko\b",
    r"\boikeudellinen velvollisuus\b",
    r"\bsitova lakilähde\b",
)
MARKDOWN_LEAK_PATTERNS = (
    r"[A-Z]:\\",
    r"F:\\",
    r"data\\raw",
    r"data/raw",
    r"\.pdf\b",
    r"\.docx?\b",
    r"\.xlsx?\b",
    r"\.dwg\b",
    r"\b(?:as\s+oy|aoy)\s+[a-zåäö]",
    r"\b[A-ZÅÄÖ][A-Za-zÅÄÖåäö-]*(?:koivu|hovi|talo)\b",
)
LONG_EXPERT_GUIDANCE_NOTE_LIMIT = 520


@dataclass(frozen=True)
class AnswerSmokeTopic:
    topic_code: str
    question: str
    topic_group: str


CORE_TOPICS = (
    AnswerSmokeTopic("payment", "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?", "core"),
    AnswerSmokeTopic(
        "wastewater_scope",
        "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?",
        "core",
    ),
    AnswerSmokeTopic(
        "stormwater_scope",
        "Mitä pitää huomioida sadevesilinjojen ja kattokaivojen sukituksessa?",
        "core",
    ),
    AnswerSmokeTopic(
        "boundaries",
        "Mitä urakkarajoissa pitää huomioida ja miten määritellään mikä kuuluu urakkaan?",
        "core",
    ),
    AnswerSmokeTopic(
        "video_inspection",
        "Mitä videotarkastuksesta ja loppukuvauksesta pitää vaatia CIPP-urakassa?",
        "core",
    ),
    AnswerSmokeTopic(
        "handover",
        "Mitä vastaanotossa pitää tarkistaa ennen CIPP-urakan hyväksymistä?",
        "core",
    ),
    AnswerSmokeTopic("warranty", "Miten takuuasiat kannattaa kirjata CIPP-sukitusurakassa?", "core"),
    AnswerSmokeTopic(
        "security_insurance",
        "Mitä vakuuksia ja vakuutuksia CIPP-urakassa pitää huomioida?",
        "core",
    ),
    AnswerSmokeTopic(
        "unit_prices_change_work",
        "Miten lisätyöt ja yksikköhinnat kannattaa määritellä sukitusurakassa?",
        "core",
    ),
    AnswerSmokeTopic(
        "defects_claims",
        "Miten puutteet, virheet ja reklamaatiot pitää dokumentoida CIPP-urakassa?",
        "core",
    ),
)
GUIDANCE_TOPICS = (
    AnswerSmokeTopic(
        "project_planning",
        "Milloin taloyhtiön kannattaa aloittaa putkiremontin hankesuunnittelu?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "board_preparation",
        "Mitä hallituksen pitää selvittää ennen putkiremontin suunnittelua?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "shareholder_questions",
        "Mitä kysymyksiä osakkaiden kannattaa esittää ennen sukituspäätöstä?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "condition_survey",
        "Milloin kuntotutkimus tai koejyrsintä tarvitaan?",
        "guidance",
    ),
    AnswerSmokeTopic("coating_risks", "Mitä riskejä pinnoitukseen liittyy?", "guidance"),
    AnswerSmokeTopic(
        "cipp_suitability",
        "Mihin sukitus soveltuu ja mitä pitää varmistaa ennen työn tilaamista?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "housing_company_decision",
        "Mitä yhtiökokouksen pitää hyväksyä ennen suunnittelun jatkamista?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "handover_warranty_guidance",
        "Mitä vastaanotossa ja takuuajassa pitää huomioida?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "authority_obligations",
        "Milloin rakennuslupa tai muu viranomaisvelvoite voi tulla mukaan?",
        "guidance",
    ),
    AnswerSmokeTopic(
        "amateur_operator_guidance",
        "Mitä amatööritoimijan pitää ymmärtää ennen kuin taloyhtiö pyytää urakkatarjouksia?",
        "guidance",
    ),
)
ANSWER_SMOKE_TOPICS = CORE_TOPICS + GUIDANCE_TOPICS


class AnswerBuilder(Protocol):
    def __call__(self, question: str) -> tuple[dict[str, Any], dict[str, Any], str]: ...


def build_answer_smoke_matrix(
    answer_builder: AnswerBuilder,
    topics: tuple[AnswerSmokeTopic, ...] = ANSWER_SMOKE_TOPICS,
    stop_on_fail: bool = False,
    include_debug: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for topic in topics:
        try:
            packet, answer, markdown = answer_builder(topic.question)
            row = evaluate_answer(topic, packet, answer, markdown, include_debug=include_debug)
        except Exception as exc:  # pragma: no cover - CLI resilience.
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


def evaluate_answer(
    topic: AnswerSmokeTopic,
    packet: dict[str, Any],
    answer: dict[str, Any],
    markdown: str,
    include_debug: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    failure_reasons: list[str] = []

    sources = list(answer.get("sources") or [])
    expert_guidance_sources_count = sum(1 for source in sources if source.get("source_class") == "expert_guidance")
    binding_law_claims = binding_law_claims_count(markdown)
    markdown_safety_status, markdown_warnings = markdown_safety(markdown)
    hallucination_status, hallucination_findings = hallucination_guard(answer, markdown)
    expert_status, expert_warnings = expert_guidance_check(answer, markdown, expert_guidance_sources_count)
    warnings.extend(markdown_warnings)
    warnings.extend(hallucination_findings)
    warnings.extend(expert_warnings)

    answer_status = str(answer.get("answer_status") or "")
    llm_used = bool(answer.get("llm_used"))
    sources_count = len(sources)
    uncertainties_count = len(answer.get("uncertainties") or [])
    missing_count = len(answer.get("missing_user_case_fields") or [])

    if llm_used:
        failure_reasons.append("llm_used must be false")
    if sources_count == 0:
        failure_reasons.append("answer has no sources")
    if binding_law_claims:
        failure_reasons.append("binding law claim detected")
    if markdown_safety_status in FAILED_STATUSES:
        failure_reasons.append("markdown safety check failed")
    if hallucination_status in FAILED_STATUSES:
        failure_reasons.append("hallucination guard failed")
    if expert_status in FAILED_STATUSES:
        failure_reasons.append("expert guidance check failed")
    if answer_status == "insufficient_evidence" and topic.topic_group == "core":
        failure_reasons.append("core topic has insufficient evidence")

    if failure_reasons:
        topic_status = "fail"
    elif answer_status == "answered":
        topic_status = "pass"
    elif answer_status == "partial" and sources_count > 0 and (uncertainties_count > 0 or missing_count > 0):
        topic_status = "partial"
    elif answer_status == "partial":
        topic_status = "fail"
        failure_reasons.append("partial answer lacks uncertainty or missing-information explanation")
    else:
        topic_status = "fail"
        failure_reasons.append(f"unsupported answer status: {answer_status}")

    row: dict[str, Any] = {
        "topic_code": topic.topic_code,
        "question": topic.question,
        "topic_group": topic.topic_group,
        "topic_status": topic_status,
        "answer_status": answer_status,
        "retrieval_status": packet.get("retrieval_status"),
        "evidence_coverage_status": packet.get("evidence_coverage_status"),
        "llm_used": llm_used,
        "sources_count": sources_count,
        "key_points_count": len(answer.get("key_points") or []),
        "uncertainties_count": uncertainties_count,
        "missing_user_case_fields_count": missing_count,
        "recommended_next_questions_count": len(answer.get("recommended_next_questions") or []),
        "expert_guidance_sources_count": expert_guidance_sources_count,
        "binding_law_claims_count": binding_law_claims,
        "markdown_safety_status": markdown_safety_status,
        "hallucination_guard_status": hallucination_status,
        "hallucination_guard_findings": hallucination_findings,
        "warnings": warnings,
        "failure_reasons": failure_reasons,
    }
    if include_debug:
        row["debug"] = {
            "detected_topics": packet.get("detected_topics"),
            "answer_generation_mode": answer.get("generation_mode"),
            "expert_guidance_check_status": expert_status,
        }
    return row


def failed_topic(topic: AnswerSmokeTopic, reason: str, include_debug: bool = False) -> dict[str, Any]:
    row = {
        "topic_code": topic.topic_code,
        "question": topic.question,
        "topic_group": topic.topic_group,
        "topic_status": "fail",
        "answer_status": "error",
        "retrieval_status": "error",
        "evidence_coverage_status": "error",
        "llm_used": False,
        "sources_count": 0,
        "key_points_count": 0,
        "uncertainties_count": 0,
        "missing_user_case_fields_count": 0,
        "recommended_next_questions_count": 0,
        "expert_guidance_sources_count": 0,
        "binding_law_claims_count": 0,
        "markdown_safety_status": "failed",
        "hallucination_guard_status": "failed",
        "hallucination_guard_findings": [reason],
        "warnings": [reason],
        "failure_reasons": [reason],
    }
    if include_debug:
        row["debug"] = {"exception": reason}
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for row in rows if row["topic_status"] == "pass")
    partial = sum(1 for row in rows if row["topic_status"] == "partial")
    failed = sum(1 for row in rows if row["topic_status"] == "fail")
    blocking = sorted(row["topic_code"] for row in rows if row["topic_status"] == "fail")
    release_candidate = (
        failed == 0
        and all(not row["llm_used"] for row in rows)
        and all(row["markdown_safety_status"] not in FAILED_STATUSES for row in rows)
        and all(row["hallucination_guard_status"] not in FAILED_STATUSES for row in rows)
        and all(row["binding_law_claims_count"] == 0 for row in rows)
    )
    return {
        "total_topics": len(rows),
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "release_candidate": release_candidate,
        "blocking_topics": blocking,
    }


def markdown_safety(markdown: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    for pattern in MARKDOWN_LEAK_PATTERNS:
        if re.search(pattern, markdown, flags=re.IGNORECASE):
            warnings.append(f"Potential markdown leak pattern matched: {pattern}")
    return ("failed" if warnings else "ok", warnings)


def binding_law_claims_count(markdown: str) -> int:
    return sum(1 for pattern in BINDING_LAW_PATTERNS if re.search(pattern, markdown, flags=re.IGNORECASE))


def expert_guidance_check(
    answer: dict[str, Any],
    markdown: str,
    expert_guidance_sources_count: int,
) -> tuple[str, list[str]]:
    if expert_guidance_sources_count == 0:
        return "ok", []
    warnings: list[str] = []
    if binding_law_claims_count(markdown):
        warnings.append("Expert guidance answer contains binding-law wording.")
    uncertainty_text = " ".join(str(item) for item in answer.get("uncertainties") or []).lower()
    if "asiantuntijaoppaaseen" not in uncertainty_text and "sitova" not in uncertainty_text:
        warnings.append("Expert guidance answer lacks binding-law uncertainty.")
    allowed_phrasing = ("asiantuntijaohjeen perusteella", "oppaan mukaan", "tämä kannattaa selvittää")
    answer_text = markdown.lower()
    if not any(phrase in answer_text for phrase in allowed_phrasing):
        warnings.append("Expert guidance answer lacks non-binding guidance phrasing.")
    return ("failed" if warnings else "ok", warnings)


def hallucination_guard(answer: dict[str, Any], markdown: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    source_text = " ".join(
        [
            *(str(note) for note in answer.get("source_based_notes") or []),
            *(str(source.get("snippet") or "") for source in answer.get("sources") or []),
        ]
    ).lower()
    for token in money_or_percent_tokens(markdown):
        if token.lower() not in source_text and "[amount redacted]" not in token.lower():
            findings.append(f"Numeric claim not found in source snippets: {token}")
    if long_expert_guidance_note(answer):
        findings.append("Expert guidance source note is too long for smoke output.")
    status = "failed" if findings else "ok"
    return status, findings


def money_or_percent_tokens(text: str) -> list[str]:
    pattern = r"\b\d[\d\s.,]*(?:€|eur|euroa?|%)\b|\b\d[\d\s.,]*\s*e(?=/|\b)"
    return [match.group(0).strip() for match in re.finditer(pattern, text, flags=re.IGNORECASE)]


def long_expert_guidance_note(answer: dict[str, Any]) -> bool:
    for note in answer.get("source_based_notes") or []:
        text = str(note)
        if "Asiantuntijaohjeen katkelma" in text and len(text) > LONG_EXPERT_GUIDANCE_NOTE_LIMIT:
            return True
    return False


def render_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Answer Composer Smoke Matrix",
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
        "| Topic | Group | Status | Answer | Retrieval | Evidence | LLM | Sources | Guidance | Safety | Guard |",
        "|---|---|---|---|---|---|---|---:|---:|---|---|",
    ]
    for row in report["topics"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md(row["topic_code"]),
                    md(row["topic_group"]),
                    md(row["topic_status"]),
                    md(row["answer_status"]),
                    md(row["retrieval_status"]),
                    md(row["evidence_coverage_status"]),
                    md(str(row["llm_used"]).lower()),
                    str(row["sources_count"]),
                    str(row["expert_guidance_sources_count"]),
                    md(row["markdown_safety_status"]),
                    md(row["hallucination_guard_status"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blocking Topics", "", list_or_none(summary["blocking_topics"]), ""])
    lines.extend(["## Expert Guidance Checks", ""])
    expert_rows = [row for row in report["topics"] if row["expert_guidance_sources_count"]]
    if not expert_rows:
        lines.append("- none")
    for row in expert_rows:
        lines.append(
            f"- `{md(row['topic_code'])}`: guidance_sources={row['expert_guidance_sources_count']}; "
            f"binding_law_claims={row['binding_law_claims_count']}"
        )
    lines.extend(["", "## Hallucination Guard Notes", ""])
    guard_rows = [row for row in report["topics"] if row["hallucination_guard_findings"]]
    if not guard_rows:
        lines.append("- none")
    for row in guard_rows:
        lines.append(f"### {md(row['topic_code'])}")
        lines.append(list_or_none(row["hallucination_guard_findings"]))
    lines.extend(["", "## Per-Topic Details", ""])
    for row in report["topics"]:
        lines.extend(
            [
                f"### {md(row['topic_code'])}",
                "",
                f"- Question: {md(row['question'])}",
                f"- Topic status: `{md(row['topic_status'])}`",
                f"- Key points: {row['key_points_count']}",
                f"- Uncertainties: {row['uncertainties_count']}",
                f"- Missing user case fields: {row['missing_user_case_fields_count']}",
                f"- Recommended next questions: {row['recommended_next_questions_count']}",
                "",
                "Warnings:",
                list_or_none(row["warnings"]),
                "",
                "Failure reasons:",
                list_or_none(row["failure_reasons"]),
                "",
            ]
        )
    lines.append("This report intentionally excludes full answer markdown and source snippets.")
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: Path | None, output_md: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_report_markdown(report) + "\n", encoding="utf-8")


def md(value: Any) -> str:
    return str(value or "").replace("|", "\\|")


def list_or_none(values: list[Any]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {md(value)}" for value in values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--stop-on-fail", action="store_true")
    parser.add_argument("--include-debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    with psycopg.connect(database_url(args.db, args.env), row_factory=dict_row) as conn:
        repository = PostgresRetrievalRepository(conn)
        limits = RetrievalLimits()

        def answer_builder(question: str) -> tuple[dict[str, Any], dict[str, Any], str]:
            packet = build_retrieval_packet(repository, question, limits=limits)
            answer = compose_answer(packet)
            return packet, answer, render_markdown(answer)

        report = build_answer_smoke_matrix(
            answer_builder,
            stop_on_fail=args.stop_on_fail,
            include_debug=args.include_debug,
        )
    if not args.dry_run:
        write_report(report, args.output, args.output_md)
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
