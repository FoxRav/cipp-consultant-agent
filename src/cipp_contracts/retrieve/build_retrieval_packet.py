from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url


ANSWER_SCOPE = "general_cipp_user_case"
REFERENCE_MODE = "internal_anonymized_grounding"
REQUIRED_PACKET_KEYS = (
    "question",
    "answer_scope",
    "user_case",
    "detected_topics",
    "missing_user_case_fields",
    "detected_entities",
    "kg_entities",
    "kg_relations",
    "evidence",
    "sections",
    "clauses",
    "raw_pages",
    "reference_usage",
    "warnings",
    "retrieval_status",
)


TOPIC_RULES: dict[str, dict[str, Any]] = {
    "payment": {
        "keywords": ("maksuerä", "maksuerät", "maksueri", "lasku", "maksuposti", "maksuerätaulukko"),
        "entity_types": ("payment_item", "contract", "document", "section", "clause"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "HAS_DOCUMENT", "HAS_SECTION", "HAS_CLAUSE"),
    },
    "finance": {
        "keywords": ("urakkahinta", "hinta", "kustannus", "€/asunto", "euro", "eur"),
        "entity_types": ("payment_item", "unit_price", "security", "insurance", "contract", "property"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "HAS_CONTRACT", "HAS_DOCUMENT"),
        "missing_fields": ("apartments_count",),
    },
    "security_insurance": {
        "keywords": ("vakuus", "vakuutus"),
        "entity_types": ("security", "insurance", "contract", "clause"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "HAS_CLAUSE"),
    },
    "quality_video": {
        "keywords": ("videotarkastus", "kuvaus", "loppukuvaus", "videokuvaus"),
        "entity_types": ("quality_requirement", "inspection", "document", "section", "clause"),
        "relation_types": ("REQUIRES", "SUPPORTED_BY", "HAS_SECTION", "HAS_CLAUSE"),
    },
    "handover": {
        "keywords": ("vastaanotto", "luovutus", "vastaanottotarkastus"),
        "entity_types": ("handover", "event", "defect", "document", "section", "clause"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "DOCUMENTED_IN", "OBSERVED_IN"),
    },
    "warranty": {
        "keywords": ("takuu", "takuutarkastus", "takuuajan"),
        "entity_types": ("warranty_issue", "quality_requirement", "defect", "clause"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "REQUIRES", "RESOLVED_BY"),
    },
    "defects_issues": {
        "keywords": ("puute", "virhe", "korjaus", "reklamaatio", "ongelma"),
        "entity_types": ("defect", "warranty_issue", "responsibility", "handover", "event", "clause"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "RESPONSIBLE_FOR", "RESOLVED_BY"),
    },
    "boundaries": {
        "keywords": ("urakkaraja", "rajaus", "kuuluuko urakkaan", "urakkaan"),
        "entity_types": ("boundary", "scope_item", "sewer_segment", "responsibility", "clause"),
        "relation_types": ("DEFINES", "AFFECTS", "SUPPORTED_BY", "RESPONSIBLE_FOR"),
    },
    "wastewater_sewer": {
        "keywords": ("jv", "jätevesi", "pystylinja", "pohjaviemäri", "tonttilinja"),
        "entity_types": ("sewer_segment", "scope_item", "boundary", "technical_requirement"),
        "relation_types": ("DEFINES", "AFFECTS", "SUPPORTED_BY", "REQUIRES"),
        "missing_fields": ("apartments_count", "jv_verticals_count"),
    },
    "stormwater_sewer": {
        "keywords": ("sv", "sadevesi", "kattokaivo", "sadevesiviemäri"),
        "entity_types": ("sewer_segment", "scope_item", "boundary", "technical_requirement"),
        "relation_types": ("DEFINES", "AFFECTS", "SUPPORTED_BY", "REQUIRES"),
        "missing_fields": ("sv_verticals_count",),
    },
    "obligations_contract_terms": {
        "keywords": ("yse", "sopimusehdot", "vastuu", "velvoite", "velvollisuus"),
        "entity_types": ("responsibility", "party", "contract", "clause", "document"),
        "relation_types": ("HAS_PARTY", "RESPONSIBLE_FOR", "SUPPORTED_BY", "HAS_CLAUSE"),
    },
    "quality_requirements": {
        "keywords": ("laatu", "laadunvarmistus", "dokumentointi"),
        "entity_types": ("quality_requirement", "technical_requirement", "inspection", "document"),
        "relation_types": ("REQUIRES", "SUPPORTED_BY", "HAS_DOCUMENT"),
    },
    "unit_prices_change_work": {
        "keywords": ("lisätyö", "yksikköhinta", "muutostyö"),
        "entity_types": ("unit_price", "payment_item", "contract", "clause"),
        "relation_types": ("CONTAINS", "SUPPORTED_BY", "HAS_CLAUSE"),
    },
}

DEFAULT_ENTITY_TYPES = (
    "scope_item",
    "boundary",
    "sewer_segment",
    "quality_requirement",
    "payment_item",
    "unit_price",
    "responsibility",
    "handover",
    "defect",
    "warranty_issue",
)
USER_CASE_FIELDS = (
    "apartments_count",
    "buildings_count",
    "staircases_count",
    "jv_verticals_count",
    "sv_verticals_count",
    "includes_bottom_drain",
    "includes_yard_line",
    "includes_video_inspection",
)


@dataclass(frozen=True)
class RetrievalLimits:
    entities: int = 10
    relations: int = 25
    evidence: int = 25
    sections: int = 20


class RetrievalRepository(Protocol):
    def search_entities(
        self,
        entity_types: list[str],
        keywords: list[str],
        limit: int,
        debug_reference_project_code: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_relations(
        self,
        entity_ids: list[str],
        relation_types: list[str],
        limit: int,
        debug_reference_project_code: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def fetch_evidence(
        self,
        entity_ids: list[str],
        relation_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def fetch_text_context(
        self,
        evidence_rows: list[dict[str, Any]],
        limit_sections: int,
    ) -> dict[str, list[dict[str, Any]]]: ...


class ReferenceAnonymizer:
    def __init__(self) -> None:
        self._labels: dict[str, str] = {}

    def label(self, project_code: str | None) -> str | None:
        if not project_code:
            return None
        if project_code not in self._labels:
            self._labels[project_code] = f"reference_{len(self._labels) + 1:03d}"
        return self._labels[project_code]

    def labels(self) -> list[str]:
        return list(self._labels.values())


class PostgresRetrievalRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def search_entities(
        self,
        entity_types: list[str],
        keywords: list[str],
        limit: int,
        debug_reference_project_code: str | None = None,
    ) -> list[dict[str, Any]]:
        patterns = [f"%{keyword}%" for keyword in keywords] or ["%"]
        rows = self.conn.execute(
            """
            SELECT
                e.id,
                e.entity_type,
                e.canonical_key,
                e.canonical_name,
                e.display_name,
                e.project_id,
                e.document_id,
                e.source_table,
                e.source_id,
                e.metadata,
                p.project_code
            FROM kg.entities e
            LEFT JOIN core.projects p ON p.id = e.project_id
            WHERE e.entity_type <> 'project'
              AND (%s::text IS NULL OR p.project_code = %s::text)
              AND (
                    e.entity_type = ANY(%s::text[])
                    OR e.canonical_name ILIKE ANY(%s::text[])
                    OR coalesce(e.display_name, '') ILIKE ANY(%s::text[])
                  )
            ORDER BY
                CASE WHEN e.entity_type = ANY(%s::text[]) THEN 0 ELSE 1 END,
                e.entity_type,
                e.canonical_name
            LIMIT %s
            """,
            (
                debug_reference_project_code,
                debug_reference_project_code,
                entity_types,
                patterns,
                patterns,
                entity_types,
                limit,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_relations(
        self,
        entity_ids: list[str],
        relation_types: list[str],
        limit: int,
        debug_reference_project_code: str | None = None,
    ) -> list[dict[str, Any]]:
        if not entity_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT
                r.id,
                r.relation_type,
                r.project_id,
                r.confidence,
                r.extraction_method,
                r.metadata,
                s.id AS subject_entity_id,
                s.entity_type AS subject_type,
                s.canonical_name AS subject_name,
                o.id AS object_entity_id,
                o.entity_type AS object_type,
                o.canonical_name AS object_name,
                p.project_code
            FROM kg.relations r
            JOIN kg.entities s ON s.id = r.subject_entity_id
            JOIN kg.entities o ON o.id = r.object_entity_id
            LEFT JOIN core.projects p ON p.id = r.project_id
            WHERE (%s::text IS NULL OR p.project_code = %s::text)
              AND (r.subject_entity_id = ANY(%s::uuid[]) OR r.object_entity_id = ANY(%s::uuid[]))
              AND (cardinality(%s::text[]) = 0 OR r.relation_type = ANY(%s))
            ORDER BY
                CASE WHEN r.relation_type = ANY(%s) THEN 0 ELSE 1 END,
                r.relation_type
            LIMIT %s
            """,
            (
                debug_reference_project_code,
                debug_reference_project_code,
                entity_ids,
                entity_ids,
                relation_types,
                relation_types,
                relation_types,
                limit,
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_evidence(
        self,
        entity_ids: list[str],
        relation_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not entity_ids and not relation_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT
                ev.id,
                ev.entity_id,
                ev.relation_id,
                ev.source_file_id,
                ev.page_id,
                ev.section_id,
                ev.clause_id,
                ev.extraction_run_id,
                ev.source_table,
                ev.source_id,
                ev.quote_text,
                ev.evidence_note,
                ev.confidence
            FROM kg.evidence ev
            WHERE ev.entity_id = ANY(%s::uuid[]) OR ev.relation_id = ANY(%s::uuid[])
            ORDER BY ev.confidence DESC, ev.created_at
            LIMIT %s
            """,
            (entity_ids, relation_ids, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_text_context(
        self,
        evidence_rows: list[dict[str, Any]],
        limit_sections: int,
    ) -> dict[str, list[dict[str, Any]]]:
        section_ids = _unique_ids(row.get("section_id") for row in evidence_rows)
        clause_ids = _unique_ids(row.get("clause_id") for row in evidence_rows)
        page_ids = _unique_ids(row.get("page_id") for row in evidence_rows)
        source_file_ids = _unique_ids(row.get("source_file_id") for row in evidence_rows)
        return {
            "sections": self._fetch_sections(section_ids, limit_sections),
            "clauses": self._fetch_clauses(clause_ids, limit_sections),
            "raw_pages": self._fetch_raw_pages(page_ids, limit_sections),
            "source_files": self._fetch_source_files(source_file_ids),
        }

    def _fetch_sections(self, section_ids: list[str], limit: int) -> list[dict[str, Any]]:
        if not section_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT
                ds.id,
                ds.title,
                ds.section_key,
                ds.body_text,
                ds.page_start,
                ds.page_end,
                ds.source_confidence,
                cd.document_type,
                cd.source_file_id,
                p.project_code
            FROM doc.sections ds
            JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
            JOIN core.contracts c ON c.id = cd.contract_id
            JOIN core.projects p ON p.id = c.project_id
            WHERE ds.id = ANY(%s::uuid[])
            ORDER BY ds.section_order
            LIMIT %s
            """,
            (section_ids, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _fetch_clauses(self, clause_ids: list[str], limit: int) -> list[dict[str, Any]]:
        if not clause_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT
                dc.id,
                dc.clause_key,
                dc.clause_type,
                dc.title,
                dc.clause_text,
                dc.source_page,
                cd.document_type,
                cd.source_file_id,
                p.project_code
            FROM doc.clauses dc
            JOIN doc.sections ds ON ds.id = dc.section_id
            JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
            JOIN core.contracts c ON c.id = cd.contract_id
            JOIN core.projects p ON p.id = c.project_id
            WHERE dc.id = ANY(%s::uuid[])
            LIMIT %s
            """,
            (clause_ids, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _fetch_raw_pages(self, page_ids: list[str], limit: int) -> list[dict[str, Any]]:
        if not page_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT
                rp.id,
                rp.source_file_id,
                rp.page_no,
                rp.raw_text,
                rp.text_quality_score,
                sf.document_type,
                sf.project_code
            FROM raw.pages rp
            JOIN raw.source_files sf ON sf.id = rp.source_file_id
            WHERE rp.id = ANY(%s::uuid[])
            ORDER BY sf.project_code, rp.page_no
            LIMIT %s
            """,
            (page_ids, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _fetch_source_files(self, source_file_ids: list[str]) -> list[dict[str, Any]]:
        if not source_file_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT id, project_code, document_type, file_ext, page_count, has_text_layer, needs_ocr
            FROM raw.source_files
            WHERE id = ANY(%s::uuid[])
            ORDER BY project_code, document_type
            """,
            (source_file_ids,),
        ).fetchall()
        return [dict(row) for row in rows]


class MemoryRetrievalRepository:
    def __init__(
        self,
        entities: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        sections: list[dict[str, Any]] | None = None,
        clauses: list[dict[str, Any]] | None = None,
        raw_pages: list[dict[str, Any]] | None = None,
    ) -> None:
        self.entities = entities or []
        self.relations = relations or []
        self.evidence = evidence or []
        self.sections = sections or []
        self.clauses = clauses or []
        self.raw_pages = raw_pages or []

    def search_entities(
        self,
        entity_types: list[str],
        keywords: list[str],
        limit: int,
        debug_reference_project_code: str | None = None,
    ) -> list[dict[str, Any]]:
        del debug_reference_project_code
        matches = []
        for row in self.entities:
            haystack = f"{row.get('canonical_name', '')} {row.get('display_name', '')}".lower()
            if row.get("entity_type") in entity_types or any(keyword in haystack for keyword in keywords):
                matches.append(row)
        return matches[:limit]

    def fetch_relations(
        self,
        entity_ids: list[str],
        relation_types: list[str],
        limit: int,
        debug_reference_project_code: str | None = None,
    ) -> list[dict[str, Any]]:
        del debug_reference_project_code
        entity_set = set(entity_ids)
        relation_type_set = set(relation_types)
        matches = [
            row
            for row in self.relations
            if (
                row.get("subject_entity_id") in entity_set
                or row.get("object_entity_id") in entity_set
            )
            and (not relation_type_set or row.get("relation_type") in relation_type_set)
        ]
        return matches[:limit]

    def fetch_evidence(
        self,
        entity_ids: list[str],
        relation_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        entity_set = set(entity_ids)
        relation_set = set(relation_ids)
        matches = [
            row
            for row in self.evidence
            if row.get("entity_id") in entity_set or row.get("relation_id") in relation_set
        ]
        return matches[:limit]

    def fetch_text_context(
        self,
        evidence_rows: list[dict[str, Any]],
        limit_sections: int,
    ) -> dict[str, list[dict[str, Any]]]:
        section_ids = set(_unique_ids(row.get("section_id") for row in evidence_rows))
        clause_ids = set(_unique_ids(row.get("clause_id") for row in evidence_rows))
        page_ids = set(_unique_ids(row.get("page_id") for row in evidence_rows))
        return {
            "sections": [row for row in self.sections if str(row.get("id")) in section_ids][
                :limit_sections
            ],
            "clauses": [row for row in self.clauses if str(row.get("id")) in clause_ids][
                :limit_sections
            ],
            "raw_pages": [row for row in self.raw_pages if str(row.get("id")) in page_ids][
                :limit_sections
            ],
            "source_files": [],
        }


def build_retrieval_packet(
    repository: RetrievalRepository,
    question: str,
    user_case: dict[str, Any] | None = None,
    topic: str | None = None,
    limits: RetrievalLimits | None = None,
    debug_reference_project_code: str | None = None,
) -> dict[str, Any]:
    limits = limits or RetrievalLimits()
    user_case = user_case or {}
    topics, detected_entities = detect_topics(question, topic)
    entity_types = entity_types_for_topics(topics)
    relation_types = relation_types_for_topics(topics)
    keywords = keywords_for_topics(topics)
    anonymizer = ReferenceAnonymizer()
    warnings = user_case_warnings(user_case, topics)
    if _looks_like_reference_project_question(question):
        warnings.append(
            "Reference projects are internal grounding material; this packet is scoped to a general CIPP user case."
        )
    if debug_reference_project_code:
        warnings.append("--debug-reference-project-code was used; this is developer-only filtering.")

    entities = repository.search_entities(
        entity_types,
        keywords,
        limits.entities,
        debug_reference_project_code=debug_reference_project_code,
    )
    entity_ids = [str(row["id"]) for row in entities]
    relations = repository.fetch_relations(
        entity_ids,
        relation_types,
        limits.relations,
        debug_reference_project_code=debug_reference_project_code,
    )
    relation_ids = [str(row["id"]) for row in relations]
    evidence_rows = repository.fetch_evidence(entity_ids, relation_ids, limits.evidence)
    context = repository.fetch_text_context(evidence_rows, limits.sections)

    packet = {
        "question": question,
        "answer_scope": ANSWER_SCOPE,
        "user_case": _jsonable_dict(user_case),
        "detected_topics": topics,
        "missing_user_case_fields": missing_user_case_fields(user_case, topics),
        "detected_entities": detected_entities,
        "kg_entities": [_public_entity(row, anonymizer) for row in entities],
        "kg_relations": [_public_relation(row, anonymizer) for row in relations],
        "evidence": [_public_evidence(row) for row in evidence_rows],
        "sections": [_public_section(row, anonymizer) for row in context.get("sections", [])],
        "clauses": [_public_clause(row, anonymizer) for row in context.get("clauses", [])],
        "raw_pages": [_public_raw_page(row, anonymizer) for row in context.get("raw_pages", [])],
        "reference_usage": {
            "mode": REFERENCE_MODE,
            "reference_projects_used": anonymizer.labels(),
        },
        "warnings": warnings,
        "retrieval_status": retrieval_status(entities, evidence_rows, context),
    }
    return {key: packet[key] for key in REQUIRED_PACKET_KEYS}


def detect_topics(question: str, explicit_topic: str | None = None) -> tuple[list[str], list[str]]:
    normalized = question.lower()
    topics: list[str] = []
    matched: list[str] = []
    if explicit_topic:
        topics.append(explicit_topic)
    for topic, rule in TOPIC_RULES.items():
        topic_matches = [keyword for keyword in rule["keywords"] if keyword in normalized]
        if topic_matches and topic not in topics:
            topics.append(topic)
            matched.extend(topic_matches)
    if not topics:
        topics.append("general_cipp")
    return topics, sorted(set(matched))


def entity_types_for_topics(topics: list[str]) -> list[str]:
    values: list[str] = []
    for topic in topics:
        values.extend(TOPIC_RULES.get(topic, {}).get("entity_types", ()))
    return sorted(set(values or DEFAULT_ENTITY_TYPES))


def relation_types_for_topics(topics: list[str]) -> list[str]:
    values: list[str] = []
    for topic in topics:
        values.extend(TOPIC_RULES.get(topic, {}).get("relation_types", ()))
    return sorted(set(values))


def keywords_for_topics(topics: list[str]) -> list[str]:
    values: list[str] = []
    for topic in topics:
        values.extend(TOPIC_RULES.get(topic, {}).get("keywords", ()))
    return sorted(set(values))


def missing_user_case_fields(user_case: dict[str, Any], topics: list[str]) -> list[str]:
    required = {"apartments_count"} if any(topic in topics for topic in ("finance", "payment")) else set()
    for topic in topics:
        required.update(TOPIC_RULES.get(topic, {}).get("missing_fields", ()))
    if "wastewater_sewer" in topics:
        required.update({"includes_bottom_drain", "includes_yard_line"})
    return sorted(field for field in required if user_case.get(field) in (None, ""))


def user_case_warnings(user_case: dict[str, Any], topics: list[str]) -> list[str]:
    missing = missing_user_case_fields(user_case, topics)
    if not missing:
        return []
    return [f"Missing user case fields for a more precise retrieval: {', '.join(missing)}."]


def build_user_case(args: argparse.Namespace) -> dict[str, Any]:
    user_case: dict[str, Any] = {}
    if args.user_case_json:
        user_case.update(json.loads(args.user_case_json.read_text(encoding="utf-8")))
    for field in USER_CASE_FIELDS:
        value = getattr(args, field)
        if value is not None:
            user_case[field] = value
    if args.topic:
        user_case["question_topic"] = args.topic
    return user_case


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Packet",
        "",
        "## Question",
        "",
        _md(packet["question"]),
        "",
        "## Answer Scope",
        "",
        _md(packet["answer_scope"]),
        "",
        "## User Case Hints",
        "",
        _json_block(packet["user_case"]),
        "",
        "## Missing User Case Fields",
        "",
        _list_or_none(packet["missing_user_case_fields"]),
        "",
        "## Detected Topics",
        "",
        _list_or_none(packet["detected_topics"]),
        "",
        "## Relevant CIPP Entities",
        "",
    ]
    for entity in packet["kg_entities"]:
        lines.append(
            f"- `{_md(entity['entity_type'])}`: {_md(entity['name'])} "
            f"({_md(entity.get('reference_label') or 'shared')})"
        )
    if not packet["kg_entities"]:
        lines.append("- none")
    lines.extend(["", "## KG Relations", ""])
    for relation in packet["kg_relations"]:
        lines.append(
            "- "
            f"{_md(relation['subject']['type'])} -> `{_md(relation['relation_type'])}` -> "
            f"{_md(relation['object']['type'])} ({_md(relation.get('reference_label') or 'shared')})"
        )
    if not packet["kg_relations"]:
        lines.append("- none")
    lines.extend(["", "## Evidence", ""])
    for evidence in packet["evidence"]:
        label = evidence.get("evidence_note") or evidence.get("source_table") or "evidence"
        lines.append(f"- {_md(label)}; confidence={_md(evidence.get('confidence'))}")
    if not packet["evidence"]:
        lines.append("- none")
    lines.extend(["", "## Source Text Snippets", ""])
    for section in packet["sections"]:
        lines.append(f"### Section: {_md(section.get('title') or section.get('section_key') or '')}")
        lines.append("")
        lines.append(_md(section.get("snippet", "")))
        lines.append("")
    for clause in packet["clauses"]:
        lines.append(f"### Clause: {_md(clause.get('title') or clause.get('clause_key') or '')}")
        lines.append("")
        lines.append(_md(clause.get("snippet", "")))
        lines.append("")
    for page in packet["raw_pages"]:
        lines.append(f"### Raw Page: {_md(page.get('reference_label') or 'reference')} p. {page.get('page_no')}")
        lines.append("")
        lines.append(_md(page.get("snippet", "")))
        lines.append("")
    if not packet["sections"] and not packet["clauses"] and not packet["raw_pages"]:
        lines.append("- none")
        lines.append("")
    lines.extend(
        [
            "## Warnings",
            "",
            _list_or_none(packet["warnings"]),
            "",
            "## Reference Usage",
            "",
            f"Mode: `{packet['reference_usage']['mode']}`",
            "",
            _list_or_none(packet["reference_usage"]["reference_projects_used"]),
            "",
            f"Retrieval status: `{packet['retrieval_status']}`",
        ]
    )
    return "\n".join(lines)


def retrieval_status(
    entities: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    context: dict[str, list[dict[str, Any]]],
) -> str:
    if not entities:
        return "no_results"
    if evidence_rows and (
        context.get("sections") or context.get("clauses") or context.get("raw_pages")
    ):
        return "ok"
    return "partial"


def write_outputs(packet: dict[str, Any], output: Path | None, output_md: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(packet) + "\n", encoding="utf-8")


def _public_entity(row: dict[str, Any], anonymizer: ReferenceAnonymizer) -> dict[str, Any]:
    return {
        "id": str(row.get("id")),
        "entity_type": row.get("entity_type"),
        "canonical_key": row.get("canonical_key"),
        "name": sanitize_text(row.get("display_name") or row.get("canonical_name") or ""),
        "reference_label": anonymizer.label(row.get("project_code")),
        "document_id": _str(row.get("document_id")),
        "source_table": row.get("source_table"),
        "source_id": _str(row.get("source_id")),
    }


def _public_relation(row: dict[str, Any], anonymizer: ReferenceAnonymizer) -> dict[str, Any]:
    return {
        "id": str(row.get("id")),
        "relation_type": row.get("relation_type"),
        "reference_label": anonymizer.label(row.get("project_code")),
        "confidence": _jsonable(row.get("confidence")),
        "subject": {
            "id": _str(row.get("subject_entity_id")),
            "type": row.get("subject_type"),
            "name": sanitize_text(row.get("subject_name") or ""),
        },
        "object": {
            "id": _str(row.get("object_entity_id")),
            "type": row.get("object_type"),
            "name": sanitize_text(row.get("object_name") or ""),
        },
    }


def _public_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _str(row.get("id")),
        "entity_id": _str(row.get("entity_id")),
        "relation_id": _str(row.get("relation_id")),
        "source_file_id": _str(row.get("source_file_id")),
        "page_id": _str(row.get("page_id")),
        "section_id": _str(row.get("section_id")),
        "clause_id": _str(row.get("clause_id")),
        "extraction_run_id": _str(row.get("extraction_run_id")),
        "source_table": row.get("source_table"),
        "source_id": _str(row.get("source_id")),
        "quote_text": snippet(row.get("quote_text")),
        "evidence_note": sanitize_text(row.get("evidence_note") or ""),
        "confidence": _jsonable(row.get("confidence")),
    }


def _public_section(row: dict[str, Any], anonymizer: ReferenceAnonymizer) -> dict[str, Any]:
    return {
        "id": _str(row.get("id")),
        "reference_label": anonymizer.label(row.get("project_code")),
        "document_type": row.get("document_type"),
        "source_file_id": _str(row.get("source_file_id")),
        "section_key": row.get("section_key"),
        "title": sanitize_text(row.get("title") or ""),
        "page_start": row.get("page_start"),
        "page_end": row.get("page_end"),
        "source_confidence": _jsonable(row.get("source_confidence")),
        "snippet": snippet(row.get("body_text")),
    }


def _public_clause(row: dict[str, Any], anonymizer: ReferenceAnonymizer) -> dict[str, Any]:
    return {
        "id": _str(row.get("id")),
        "reference_label": anonymizer.label(row.get("project_code")),
        "document_type": row.get("document_type"),
        "source_file_id": _str(row.get("source_file_id")),
        "clause_key": row.get("clause_key"),
        "clause_type": row.get("clause_type"),
        "title": sanitize_text(row.get("title") or ""),
        "source_page": row.get("source_page"),
        "snippet": snippet(row.get("clause_text")),
    }


def _public_raw_page(row: dict[str, Any], anonymizer: ReferenceAnonymizer) -> dict[str, Any]:
    return {
        "id": _str(row.get("id")),
        "reference_label": anonymizer.label(row.get("project_code")),
        "document_type": row.get("document_type"),
        "source_file_id": _str(row.get("source_file_id")),
        "page_no": row.get("page_no"),
        "text_quality_score": _jsonable(row.get("text_quality_score")),
        "snippet": snippet(row.get("raw_text")),
    }


def snippet(value: Any, max_length: int = 600) -> str:
    text = sanitize_text(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def sanitize_text(value: str) -> str:
    text = str(value)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "[email redacted]", text)
    text = re.sub(
        r"Source file id:\s*`?[^`\s]+`?\s+Extractor:\s*`?[^`\s]+`?\s+Extractor status:\s*`?[^`\s]+`?",
        "[source metadata redacted]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"Extractor:\s*`?[^`\s]+`?", "Extractor: [extractor redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[phone redacted]", text)
    text = re.sub(
        r"[^\n]{0,100}\.(?:pdf|docx?|xlsx?|xls|dwg)",
        "[document redacted]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:As(?:unto)?\.?\s+Oy|AOY)\s+[A-ZÅÄÖ][A-Za-zÅÄÖåäö0-9 .'-]{2,60}",
        "As Oy [redacted]",
        text,
    )
    return text


def _looks_like_reference_project_question(question: str) -> bool:
    normalized = question.lower()
    return any(
        marker in normalized
        for marker in ("referenssiprojekti", "reference_", "pilot_", "projektissa ")
    )


def _unique_ids(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _jsonable_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in values.items()}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|")


def _list_or_none(values: list[Any]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {_md(value)}" for value in values)


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n```"


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "kyllä", "k"}:
        return True
    if normalized in {"0", "false", "no", "n", "ei", "e"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--user-case-json", type=Path)
    parser.add_argument("--apartments-count", type=int)
    parser.add_argument("--buildings-count", type=int)
    parser.add_argument("--staircases-count", type=int)
    parser.add_argument("--jv-verticals-count", type=int)
    parser.add_argument("--sv-verticals-count", type=int)
    parser.add_argument("--includes-bottom-drain", type=parse_bool)
    parser.add_argument("--includes-yard-line", type=parse_bool)
    parser.add_argument("--includes-video-inspection", type=parse_bool)
    parser.add_argument("--topic")
    parser.add_argument("--limit-entities", type=int, default=10)
    parser.add_argument("--limit-relations", type=int, default=25)
    parser.add_argument("--limit-evidence", type=int, default=25)
    parser.add_argument("--limit-sections", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug-reference-project-code")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    limits = RetrievalLimits(
        entities=args.limit_entities,
        relations=args.limit_relations,
        evidence=args.limit_evidence,
        sections=args.limit_sections,
    )
    with psycopg.connect(database_url(args.db, args.env), row_factory=dict_row) as conn:
        packet = build_retrieval_packet(
            PostgresRetrievalRepository(conn),
            args.question,
            user_case=build_user_case(args),
            topic=args.topic,
            limits=limits,
            debug_reference_project_code=args.debug_reference_project_code,
        )
    if not args.dry_run:
        write_outputs(packet, args.output, args.output_md)
    print(json.dumps({"retrieval_status": packet["retrieval_status"], "detected_topics": packet["detected_topics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
