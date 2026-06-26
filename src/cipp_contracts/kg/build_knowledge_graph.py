from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url


MIGRATION_PATH = Path(__file__).resolve().parents[3] / "db" / "migrations" / "008_knowledge_graph.sql"
EXTRACTION_METHOD = "structured_postgres_v0.4"


@dataclass(frozen=True)
class EvidenceRef:
    source_table: str | None = None
    source_id: str | None = None
    source_file_id: str | None = None
    page_id: str | None = None
    section_id: str | None = None
    clause_id: str | None = None
    extraction_run_id: str | None = None
    quote_text: str | None = None
    evidence_note: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class EntitySpec:
    entity_type: str
    canonical_key: str
    canonical_name: str
    display_name: str | None = None
    project_id: str | None = None
    document_id: str | None = None
    source_table: str | None = None
    source_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: EvidenceRef | None = None


@dataclass(frozen=True)
class RelationSpec:
    subject_key: tuple[str, str]
    relation_type: str
    object_key: tuple[str, str]
    project_id: str | None = None
    confidence: float = 1.0
    extraction_method: str = EXTRACTION_METHOD
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: EvidenceRef | None = None


@dataclass
class BuildStats:
    projects: int = 0
    entities_seen: int = 0
    relations_seen: int = 0
    evidence_seen: int = 0
    entities_written: int = 0
    relations_written: int = 0
    evidence_written: int = 0


class GraphStore(Protocol):
    dry_run: bool

    def upsert_entity(self, spec: EntitySpec) -> str: ...

    def upsert_relation(self, spec: RelationSpec) -> str: ...

    def add_entity_evidence(self, entity_id: str, evidence: EvidenceRef) -> None: ...

    def add_relation_evidence(self, relation_id: str, evidence: EvidenceRef) -> None: ...


class PostgresGraphStore:
    def __init__(self, conn: psycopg.Connection[Any], dry_run: bool = False) -> None:
        self.conn = conn
        self.dry_run = dry_run
        self.entity_ids: dict[tuple[str, str], str] = {}
        self.relation_ids: dict[tuple[str, str, str, str, str], str] = {}
        self.stats = BuildStats()

    def upsert_entity(self, spec: EntitySpec) -> str:
        self.stats.entities_seen += 1
        cache_key = (spec.entity_type, spec.canonical_key)
        if cache_key in self.entity_ids:
            return self.entity_ids[cache_key]
        if self.dry_run:
            entity_id = f"dry:entity:{spec.entity_type}:{spec.canonical_key}"
            self.entity_ids[cache_key] = entity_id
            return entity_id
        row = self.conn.execute(
            """
            INSERT INTO kg.entities (
                entity_type, canonical_key, canonical_name, display_name,
                project_id, document_id, source_table, source_id, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (entity_type, canonical_key) DO UPDATE
            SET canonical_name = EXCLUDED.canonical_name,
                display_name = EXCLUDED.display_name,
                project_id = EXCLUDED.project_id,
                document_id = EXCLUDED.document_id,
                source_table = EXCLUDED.source_table,
                source_id = EXCLUDED.source_id,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                spec.entity_type,
                spec.canonical_key,
                spec.canonical_name,
                spec.display_name,
                spec.project_id,
                spec.document_id,
                spec.source_table,
                spec.source_id,
                Jsonb(spec.metadata),
            ),
        ).fetchone()
        entity_id = str(row["id"])
        self.entity_ids[cache_key] = entity_id
        self.stats.entities_written += 1
        return entity_id

    def upsert_relation(self, spec: RelationSpec) -> str:
        self.stats.relations_seen += 1
        subject_id = self.entity_ids[spec.subject_key]
        object_id = self.entity_ids[spec.object_key]
        cache_key = (subject_id, spec.relation_type, object_id, spec.subject_key[1], spec.object_key[1])
        if cache_key in self.relation_ids:
            return self.relation_ids[cache_key]
        if self.dry_run:
            relation_id = f"dry:relation:{subject_id}:{spec.relation_type}:{object_id}"
            self.relation_ids[cache_key] = relation_id
            return relation_id
        row = self.conn.execute(
            """
            INSERT INTO kg.relations (
                subject_entity_id, relation_type, object_entity_id,
                project_id, confidence, extraction_method, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (subject_entity_id, relation_type, object_entity_id) DO UPDATE
            SET project_id = EXCLUDED.project_id,
                confidence = EXCLUDED.confidence,
                extraction_method = EXCLUDED.extraction_method,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                subject_id,
                spec.relation_type,
                object_id,
                spec.project_id,
                spec.confidence,
                spec.extraction_method,
                Jsonb(spec.metadata),
            ),
        ).fetchone()
        relation_id = str(row["id"])
        self.relation_ids[cache_key] = relation_id
        self.stats.relations_written += 1
        return relation_id

    def add_entity_evidence(self, entity_id: str, evidence: EvidenceRef) -> None:
        self.stats.evidence_seen += 1
        if self.dry_run:
            return
        self._replace_evidence(entity_id=entity_id, relation_id=None, evidence=evidence)
        self.stats.evidence_written += 1

    def add_relation_evidence(self, relation_id: str, evidence: EvidenceRef) -> None:
        self.stats.evidence_seen += 1
        if self.dry_run:
            return
        self._replace_evidence(entity_id=None, relation_id=relation_id, evidence=evidence)
        self.stats.evidence_written += 1

    def _replace_evidence(
        self,
        entity_id: str | None,
        relation_id: str | None,
        evidence: EvidenceRef,
    ) -> None:
        self.conn.execute(
            """
            DELETE FROM kg.evidence
            WHERE entity_id IS NOT DISTINCT FROM %s
              AND relation_id IS NOT DISTINCT FROM %s
              AND source_table IS NOT DISTINCT FROM %s
              AND source_id IS NOT DISTINCT FROM %s
              AND source_file_id IS NOT DISTINCT FROM %s
              AND page_id IS NOT DISTINCT FROM %s
              AND section_id IS NOT DISTINCT FROM %s
              AND clause_id IS NOT DISTINCT FROM %s
              AND extraction_run_id IS NOT DISTINCT FROM %s
            """,
            (
                entity_id,
                relation_id,
                evidence.source_table,
                evidence.source_id,
                evidence.source_file_id,
                evidence.page_id,
                evidence.section_id,
                evidence.clause_id,
                evidence.extraction_run_id,
            ),
        )
        self.conn.execute(
            """
            INSERT INTO kg.evidence (
                entity_id, relation_id, source_file_id, page_id, section_id, clause_id,
                extraction_run_id, source_table, source_id, quote_text, evidence_note, confidence
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                entity_id,
                relation_id,
                evidence.source_file_id,
                evidence.page_id,
                evidence.section_id,
                evidence.clause_id,
                evidence.extraction_run_id,
                evidence.source_table,
                evidence.source_id,
                evidence.quote_text,
                evidence.evidence_note,
                evidence.confidence,
            ),
        )


class MemoryGraphStore:
    dry_run = False

    def __init__(self) -> None:
        self.entities: dict[tuple[str, str], EntitySpec] = {}
        self.relations: dict[tuple[tuple[str, str], str, tuple[str, str]], RelationSpec] = {}
        self.entity_evidence: list[tuple[str, EvidenceRef]] = []
        self.relation_evidence: list[tuple[str, EvidenceRef]] = []

    def upsert_entity(self, spec: EntitySpec) -> str:
        self.entities[(spec.entity_type, spec.canonical_key)] = spec
        return f"entity:{spec.entity_type}:{spec.canonical_key}"

    def upsert_relation(self, spec: RelationSpec) -> str:
        self.relations[(spec.subject_key, spec.relation_type, spec.object_key)] = spec
        return f"relation:{spec.subject_key}:{spec.relation_type}:{spec.object_key}"

    def add_entity_evidence(self, entity_id: str, evidence: EvidenceRef) -> None:
        self.entity_evidence.append((entity_id, evidence))

    def add_relation_evidence(self, relation_id: str, evidence: EvidenceRef) -> None:
        self.relation_evidence.append((relation_id, evidence))


def ensure_schema(conn: psycopg.Connection[Any]) -> None:
    conn.execute(MIGRATION_PATH.read_text(encoding="utf-8"))


def prune_project(conn: psycopg.Connection[Any], project_code: str) -> None:
    row = conn.execute("SELECT id FROM core.projects WHERE project_code = %s", (project_code,)).fetchone()
    if not row:
        return
    conn.execute("DELETE FROM kg.entities WHERE project_id = %s", (row["id"],))


def build_graph_from_dataset(store: GraphStore, data: dict[str, list[dict[str, Any]]]) -> BuildStats:
    stats = BuildStats(projects=len(data.get("projects", [])))
    contract_project: dict[str, str] = {}
    document_project: dict[str, str] = {}
    section_document: dict[str, str] = {}
    section_project: dict[str, str] = {}
    scope_by_contract_system: dict[tuple[str, str], tuple[str, str]] = {}

    for project in data.get("projects", []):
        project_key = _key("project", project["project_code"])
        _entity(
            store,
            stats,
            EntitySpec(
                "project",
                project_key,
                project["project_code"],
                project.get("project_name_redacted"),
                project_id=_id(project),
                source_table="core.projects",
                source_id=_id(project),
                metadata={"project_type": project.get("project_type")},
                evidence=EvidenceRef("core.projects", _id(project), evidence_note="Project row."),
            ),
        )

    for prop in data.get("properties", []):
        project_key = _project_key_by_id(data, prop["project_id"])
        prop_key = _key("property", prop["id"])
        _entity(
            store,
            stats,
            EntitySpec(
                "property",
                prop_key,
                prop.get("property_code", "property"),
                project_id=prop["project_id"],
                source_table="core.properties",
                source_id=_id(prop),
                metadata={k: _jsonable(prop.get(k)) for k in ("apartment_count", "building_count", "floor_area_m2")},
                evidence=EvidenceRef("core.properties", _id(prop), evidence_note="Property row."),
            ),
        )
        _relation(store, stats, RelationSpec(project_key, "CONTAINS", ("property", prop_key), prop["project_id"]))

    for contract in data.get("contracts", []):
        project_key = _project_key_by_id(data, contract["project_id"])
        contract_key = _key("contract", contract["id"])
        contract_project[_id(contract)] = _str(contract["project_id"])
        _entity(
            store,
            stats,
            EntitySpec(
                "contract",
                contract_key,
                contract.get("contract_code", _id(contract)),
                project_id=contract["project_id"],
                source_table="core.contracts",
                source_id=_id(contract),
                metadata={"contract_type": contract.get("contract_type")},
                evidence=EvidenceRef("core.contracts", _id(contract), evidence_note="Contract row."),
            ),
        )
        _relation(store, stats, RelationSpec(project_key, "HAS_CONTRACT", ("contract", contract_key), contract["project_id"]))

    for party in data.get("parties", []):
        party_key = _key("party", party["id"])
        _entity(
            store,
            stats,
            EntitySpec(
                "party",
                party_key,
                party.get("display_name_redacted", party.get("party_code", _id(party))),
                source_table="core.parties",
                source_id=_id(party),
                metadata={"party_type": party.get("party_type")},
                evidence=EvidenceRef("core.parties", _id(party), evidence_note="Party row."),
            ),
        )

    for cp in data.get("contract_parties", []):
        contract_key = _key("contract", cp["contract_id"])
        party_key = _key("party", cp["party_id"])
        project_id = contract_project.get(_str(cp["contract_id"]))
        _relation(
            store,
            stats,
            RelationSpec(
                ("contract", contract_key),
                "HAS_PARTY",
                ("party", party_key),
                project_id,
                metadata={"role": cp.get("role")},
                evidence=EvidenceRef("core.contract_parties", _id(cp), evidence_note="Contract party row."),
            ),
        )

    for doc in data.get("documents", []):
        contract_key = _key("contract", doc["contract_id"])
        project_id = contract_project.get(_str(doc["contract_id"]))
        doc_key = _key("document", doc["id"])
        document_project[_id(doc)] = project_id or ""
        _entity(
            store,
            stats,
            EntitySpec(
                "document",
                doc_key,
                doc.get("document_title_redacted") or doc.get("document_type") or _id(doc),
                project_id=project_id,
                document_id=_id(doc),
                source_table="core.contract_documents",
                source_id=_id(doc),
                metadata={"document_type": doc.get("document_type"), "attachment_no": doc.get("attachment_no")},
                evidence=EvidenceRef(
                    "core.contract_documents",
                    _id(doc),
                    source_file_id=_str(doc.get("source_file_id")),
                    evidence_note="Contract document row.",
                ),
            ),
        )
        if project_id:
            project_code_key = _project_key_by_id(data, project_id)
            _relation(store, stats, RelationSpec(project_code_key, "HAS_DOCUMENT", ("document", doc_key), project_id))
        _relation(store, stats, RelationSpec(("contract", contract_key), "HAS_DOCUMENT", ("document", doc_key), project_id))

    for section in data.get("sections", []):
        doc_key = _key("document", section["contract_document_id"])
        section_key = _key("section", section["id"])
        project_id = document_project.get(_str(section["contract_document_id"]))
        section_document[_id(section)] = _str(section["contract_document_id"])
        section_project[_id(section)] = project_id or ""
        _entity(
            store,
            stats,
            EntitySpec(
                "section",
                section_key,
                section.get("title") or section.get("section_key") or _id(section),
                project_id=project_id,
                document_id=section["contract_document_id"],
                source_table="doc.sections",
                source_id=_id(section),
                metadata={"section_key": section.get("section_key"), "page_start": section.get("page_start")},
                evidence=EvidenceRef("doc.sections", _id(section), section_id=_id(section), evidence_note="Document section row."),
            ),
        )
        _relation(
            store,
            stats,
            RelationSpec(("document", doc_key), "HAS_SECTION", ("section", section_key), project_id, evidence=EvidenceRef("doc.sections", _id(section), section_id=_id(section))),
        )

    for clause in data.get("clauses", []):
        section_key = _key("section", clause["section_id"])
        clause_key = _key("clause", clause["id"])
        document_id = section_document.get(_str(clause["section_id"]))
        project_id = section_project.get(_str(clause["section_id"]))
        _entity(
            store,
            stats,
            EntitySpec(
                "clause",
                clause_key,
                clause.get("title") or clause.get("clause_key") or _id(clause),
                project_id=project_id,
                document_id=document_id,
                source_table="doc.clauses",
                source_id=_id(clause),
                metadata={"clause_type": clause.get("clause_type"), "source_page": clause.get("source_page")},
                evidence=EvidenceRef("doc.clauses", _id(clause), clause_id=_id(clause), evidence_note="Document clause row."),
            ),
        )
        _relation(
            store,
            stats,
            RelationSpec(("section", section_key), "HAS_CLAUSE", ("clause", clause_key), project_id, evidence=EvidenceRef("doc.clauses", _id(clause), clause_id=_id(clause))),
        )

    for row in data.get("scope_items", []):
        entity_key = _key("scope_item", row["id"])
        project_id = contract_project.get(_str(row["contract_id"]))
        scope_by_contract_system[(_str(row["contract_id"]), row.get("system_type"))] = ("scope_item", entity_key)
        _simple_contract_child(store, stats, row, "scope_item", entity_key, "domain.scope_items", "DEFINES", "item_name", project_id)

    for row in data.get("boundaries", []):
        entity_key = _key("boundary", row["id"])
        project_id = contract_project.get(_str(row["contract_id"]))
        _simple_contract_child(store, stats, row, "boundary", entity_key, "domain.contract_boundaries", "DEFINES", "system_type", project_id)

    for row in data.get("sewer_segments", []):
        entity_key = _key("sewer_segment", row["id"])
        project_id = contract_project.get(_str(row["contract_id"]))
        _simple_contract_child(store, stats, row, "sewer_segment", entity_key, "domain.sewer_segments", "DEFINES", "segment_name", project_id)
        scope_key = scope_by_contract_system.get((_str(row["contract_id"]), row.get("system_type")))
        if scope_key:
            _relation(store, stats, RelationSpec(scope_key, "AFFECTS", ("sewer_segment", entity_key), project_id, evidence=EvidenceRef("domain.sewer_segments", _id(row), evidence_note="Scope system affects sewer segment.")))

    for row in data.get("responsibilities", []):
        project_id = contract_project.get(_str(row["contract_id"]))
        entity_key = _key("responsibility", row["id"])
        _simple_contract_child(store, stats, row, "responsibility", entity_key, "domain.responsibility_matrix", "DEFINES", "responsibility_area", project_id)

    for row in data.get("technical_requirements", []):
        _simple_contract_child(store, stats, row, "technical_requirement", _key("technical_requirement", row["id"]), "domain.technical_requirements", "REQUIRES", "requirement_text", contract_project.get(_str(row["contract_id"])))

    for row in data.get("quality_requirements", []):
        _simple_contract_child(store, stats, row, "quality_requirement", _key("quality_requirement", row["id"]), "quality.requirements", "REQUIRES", "requirement_text", contract_project.get(_str(row["contract_id"])))

    for row in data.get("quality_inspections", []):
        _simple_contract_child(store, stats, row, "inspection", _key("inspection", row["id"]), "quality.inspections", "REQUIRES", "inspection_text", contract_project.get(_str(row["contract_id"])))

    for row in data.get("quality_defects", []):
        _simple_contract_child(store, stats, row, "defect", _key("defect", row["id"]), "quality.defects", "CONTAINS", "issue_text", contract_project.get(_str(row["contract_id"])))

    for row in data.get("payment_items", []):
        _simple_contract_child(store, stats, row, "payment_item", _key("payment_item", row["id"]), "finance.payment_schedule_items", "CONTAINS", "payment_condition", contract_project.get(_str(row["contract_id"])), document_id=_str(row.get("source_document_id")))

    for row in data.get("unit_prices", []):
        _simple_contract_child(store, stats, row, "unit_price", _key("unit_price", row["id"]), "finance.unit_prices", "CONTAINS", "item_name", contract_project.get(_str(row["contract_id"])))

    for row in data.get("securities", []):
        _simple_contract_child(store, stats, row, "security", _key("security", row["id"]), "finance.securities", "CONTAINS", "security_type", contract_project.get(_str(row["contract_id"])))

    for row in data.get("insurances", []):
        _simple_contract_child(store, stats, row, "insurance", _key("insurance", row["id"]), "finance.insurances", "CONTAINS", "insurance_type", contract_project.get(_str(row["contract_id"])))

    for row in data.get("events", []):
        project_key = _project_key_by_code(data, row["project_code"])
        entity_key = _key("event", row["id"])
        _entity(store, stats, EntitySpec("event", entity_key, row.get("title") or _id(row), project_id=_project_id_by_code(data, row["project_code"]), source_table="ops.project_events", source_id=_id(row), metadata={"event_type": row.get("event_type"), "event_date": _jsonable(row.get("event_date"))}, evidence=EvidenceRef("ops.project_events", _id(row), source_file_id=_str(row.get("source_file_id")), evidence_note="Operational event row.")))
        _relation(store, stats, RelationSpec(project_key, "CONTAINS", ("event", entity_key), _project_id_by_code(data, row["project_code"])))

    for row in data.get("handover_records", []):
        project_key = _project_key_by_code(data, row["project_code"])
        entity_key = _key("handover", row["id"])
        project_id = _project_id_by_code(data, row["project_code"])
        _entity(store, stats, EntitySpec("handover", entity_key, row.get("handover_summary") or "handover", project_id=project_id, source_table="ops.handover_records", source_id=_id(row), metadata={"handover_date": _jsonable(row.get("handover_date")), "accepted": row.get("accepted")}, evidence=EvidenceRef("ops.handover_records", _id(row), source_file_id=_str(row.get("source_file_id")), evidence_note="Handover row.")))
        _relation(store, stats, RelationSpec(project_key, "CONTAINS", ("handover", entity_key), project_id))

    for row in data.get("observations", []):
        project_key = _project_key_by_code(data, row["project_code"])
        entity_type = "warranty_issue" if row.get("observation_type") == "warranty" else "defect"
        entity_key = _key(entity_type, row["id"])
        project_id = _project_id_by_code(data, row["project_code"])
        _entity(store, stats, EntitySpec(entity_type, entity_key, row.get("issue_text") or entity_type, project_id=project_id, source_table="ops.project_observations", source_id=_id(row), metadata={"observation_type": row.get("observation_type"), "status": row.get("status")}, evidence=EvidenceRef("ops.project_observations", _id(row), source_file_id=_str(row.get("source_file_id")), evidence_note="Operational observation row.")))
        _relation(store, stats, RelationSpec(project_key, "CONTAINS", (entity_type, entity_key), project_id))

    return stats


def _simple_contract_child(
    store: GraphStore,
    stats: BuildStats,
    row: dict[str, Any],
    entity_type: str,
    entity_key: str,
    source_table: str,
    relation_type: str,
    name_field: str,
    project_id: str | None,
    document_id: str | None = None,
) -> None:
    contract_key = _key("contract", row["contract_id"])
    source_clause_id = _str(row.get("source_clause_id"))
    evidence = EvidenceRef(
        source_table,
        _id(row),
        clause_id=source_clause_id,
        source_file_id=_str(row.get("source_file_id")),
        evidence_note=f"{source_table} row.",
    )
    _entity(
        store,
        stats,
        EntitySpec(
            entity_type,
            entity_key,
            str(row.get(name_field) or row.get("item_no") or row.get("requirement_key") or _id(row)),
            project_id=project_id,
            document_id=document_id,
            source_table=source_table,
            source_id=_id(row),
            metadata={key: _jsonable(value) for key, value in row.items() if key not in {"id"}},
            evidence=evidence,
        ),
    )
    _relation(store, stats, RelationSpec(("contract", contract_key), relation_type, (entity_type, entity_key), project_id, evidence=evidence))
    if document_id:
        _relation(
            store,
            stats,
            RelationSpec((entity_type, entity_key), "SUPPORTED_BY", ("document", _key("document", document_id)), project_id, evidence=evidence),
        )
    if source_clause_id:
        _relation(
            store,
            stats,
            RelationSpec((entity_type, entity_key), "SUPPORTED_BY", ("clause", _key("clause", source_clause_id)), project_id, evidence=evidence),
        )


def _entity(store: GraphStore, stats: BuildStats, spec: EntitySpec) -> str:
    entity_id = store.upsert_entity(spec)
    stats.entities_seen += 1
    if spec.evidence:
        store.add_entity_evidence(entity_id, spec.evidence)
        stats.evidence_seen += 1
    return entity_id


def _relation(store: GraphStore, stats: BuildStats, spec: RelationSpec) -> str:
    relation_id = store.upsert_relation(spec)
    stats.relations_seen += 1
    evidence = spec.evidence or EvidenceRef("kg.derived", evidence_note=f"Derived from structured relation {spec.relation_type}.")
    store.add_relation_evidence(relation_id, evidence)
    stats.evidence_seen += 1
    return relation_id


def fetch_dataset(conn: psycopg.Connection[Any], project_code: str | None = None) -> dict[str, list[dict[str, Any]]]:
    project_filter = "WHERE p.project_code = %s" if project_code else ""
    params: tuple[Any, ...] = (project_code,) if project_code else ()
    projects = _fetch(conn, f"SELECT * FROM core.projects p {project_filter} ORDER BY p.project_code", params)
    project_ids = [row["id"] for row in projects]
    if not project_ids:
        return {"projects": []}
    return {
        "projects": projects,
        "properties": _fetch(conn, "SELECT * FROM core.properties WHERE project_id = ANY(%s)", (project_ids,)),
        "contracts": _fetch(conn, "SELECT * FROM core.contracts WHERE project_id = ANY(%s)", (project_ids,)),
        "parties": _fetch(conn, """
            SELECT DISTINCT pa.*
            FROM core.parties pa
            JOIN core.contract_parties cp ON cp.party_id = pa.id
            JOIN core.contracts c ON c.id = cp.contract_id
            WHERE c.project_id = ANY(%s)
        """, (project_ids,)),
        "contract_parties": _fetch(conn, """
            SELECT cp.*
            FROM core.contract_parties cp
            JOIN core.contracts c ON c.id = cp.contract_id
            WHERE c.project_id = ANY(%s)
        """, (project_ids,)),
        "documents": _fetch(conn, """
            SELECT cd.*
            FROM core.contract_documents cd
            JOIN core.contracts c ON c.id = cd.contract_id
            WHERE c.project_id = ANY(%s)
        """, (project_ids,)),
        "sections": _fetch(conn, """
            SELECT ds.*
            FROM doc.sections ds
            JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
            JOIN core.contracts c ON c.id = cd.contract_id
            WHERE c.project_id = ANY(%s)
        """, (project_ids,)),
        "clauses": _fetch(conn, """
            SELECT dc.*
            FROM doc.clauses dc
            JOIN doc.sections ds ON ds.id = dc.section_id
            JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
            JOIN core.contracts c ON c.id = cd.contract_id
            WHERE c.project_id = ANY(%s)
        """, (project_ids,)),
        "scope_items": _contract_rows(conn, "domain.scope_items", project_ids),
        "boundaries": _contract_rows(conn, "domain.contract_boundaries", project_ids),
        "sewer_segments": _contract_rows(conn, "domain.sewer_segments", project_ids),
        "responsibilities": _contract_rows(conn, "domain.responsibility_matrix", project_ids),
        "technical_requirements": _contract_rows(conn, "domain.technical_requirements", project_ids),
        "quality_requirements": _contract_rows(conn, "quality.requirements", project_ids),
        "quality_inspections": _contract_rows(conn, "quality.inspections", project_ids),
        "quality_defects": _contract_rows(conn, "quality.defects", project_ids),
        "payment_items": _contract_rows(conn, "finance.payment_schedule_items", project_ids),
        "unit_prices": _contract_rows(conn, "finance.unit_prices", project_ids),
        "securities": _contract_rows(conn, "finance.securities", project_ids),
        "insurances": _contract_rows(conn, "finance.insurances", project_ids),
        "events": _ops_rows(conn, "ops.project_events", projects),
        "handover_records": _ops_rows(conn, "ops.handover_records", projects),
        "observations": _ops_rows(conn, "ops.project_observations", projects),
    }


def build_knowledge_graph(
    db_url: str,
    project_code: str | None,
    all_projects: bool,
    dry_run: bool,
    prune: bool,
) -> BuildStats:
    if not all_projects and not project_code:
        raise ValueError("Use --all or --project-code.")
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        ensure_schema(conn)
        if prune and project_code and not dry_run:
            prune_project(conn, project_code)
        elif prune and all_projects and not dry_run:
            conn.execute("DELETE FROM kg.entities")
        data = fetch_dataset(conn, project_code)
        store = PostgresGraphStore(conn, dry_run=dry_run)
        stats = build_graph_from_dataset(store, data)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
            stats.entities_written = store.stats.entities_written
            stats.relations_written = store.stats.relations_written
            stats.evidence_written = store.stats.evidence_written
        return stats


def _contract_rows(conn: psycopg.Connection[Any], table: str, project_ids: list[Any]) -> list[dict[str, Any]]:
    if not _table_exists(conn, table):
        return []
    return _fetch(conn, f"""
        SELECT t.*
        FROM {table} t
        JOIN core.contracts c ON c.id = t.contract_id
        WHERE c.project_id = ANY(%s)
    """, (project_ids,))


def _ops_rows(conn: psycopg.Connection[Any], table: str, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not _table_exists(conn, table):
        return []
    codes = [project["project_code"] for project in projects]
    return _fetch(conn, f"SELECT * FROM {table} WHERE project_code = ANY(%s)", (codes,))


def _table_exists(conn: psycopg.Connection[Any], table: str) -> bool:
    schema, name = table.split(".", 1)
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, name),
    ).fetchone()
    return bool(row)


def _fetch(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _project_key_by_id(data: dict[str, list[dict[str, Any]]], project_id: str) -> tuple[str, str]:
    for project in data.get("projects", []):
        if _id(project) == str(project_id):
            return "project", _key("project", project["project_code"])
    raise KeyError(f"Project not in dataset: {project_id}")


def _project_key_by_code(data: dict[str, list[dict[str, Any]]], project_code: str) -> tuple[str, str]:
    return "project", _key("project", project_code)


def _project_id_by_code(data: dict[str, list[dict[str, Any]]], project_code: str) -> str | None:
    for project in data.get("projects", []):
        if project["project_code"] == project_code:
            return _id(project)
    return None


def _key(prefix: str, value: Any) -> str:
    return f"{prefix}:{value}"


def _id(row: dict[str, Any]) -> str:
    return str(row["id"])


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project-code")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    stats = build_knowledge_graph(
        database_url(args.db, args.env),
        project_code=args.project_code,
        all_projects=args.all,
        dry_run=args.dry_run,
        prune=args.prune,
    )
    mode = "dry-run" if args.dry_run else "written"
    print(
        "Knowledge graph build "
        f"{mode}: projects={stats.projects}, entities={stats.entities_seen}, "
        f"relations={stats.relations_seen}, evidence={stats.evidence_seen}"
    )


if __name__ == "__main__":
    main()
