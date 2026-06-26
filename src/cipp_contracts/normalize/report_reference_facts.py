from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url
from cipp_contracts.extract.report_processing_quality import project_summary


FACT_FIELDS = [
    "project_code",
    "project_display_name",
    "source_coverage_status",
    "text_layer_status",
    "apartments_count",
    "buildings_count",
    "staircases_count",
    "floors_count",
    "floor_area_m2",
    "business_premises_count",
    "jv_verticals_count",
    "sv_verticals_count",
    "jv_scope_summary",
    "sv_scope_summary",
    "bottom_drain_scope",
    "yard_line_scope",
    "contract_price",
    "payment_schedule_total",
    "payment_schedule_matches_contract_price",
    "price_per_apartment",
    "unit_prices_available",
    "securities_available",
    "insurance_available",
    "quality_requirements_available",
    "video_inspection_available",
    "handover_or_reception_available",
    "defects_or_open_items_count",
    "warranty_notes_available",
    "missing_fields",
    "weak_evidence_fields",
    "blocking_missing_fields",
    "blocking_weak_evidence_fields",
    "kg_readiness_reasons",
    "confidence_summary",
    "kg_readiness_status",
]

KG_BLOCKING_MISSING_FIELDS = {
    "apartments_count",
    "jv_verticals_count",
    "jv_scope_summary",
    "bottom_drain_scope",
    "yard_line_scope",
    "contract_price",
    "payment_schedule_total",
    "quality_requirements_available",
    "video_inspection_available",
    "handover_or_reception_available",
    "warranty_notes_available",
}

KG_BLOCKING_WEAK_FIELDS = {
    "contract_price",
    "payment_schedule_total",
    "payment_schedule_matches_contract_price",
    "apartments_count",
    "jv_verticals_count",
    "jv_scope_summary",
    "bottom_drain_scope",
    "yard_line_scope",
}


@dataclass
class ReferenceFacts:
    values: dict[str, Any]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    weak_evidence_fields: list[str] = field(default_factory=list)


def evidence(
    field_name: str,
    value: Any,
    source_table: str,
    source_column: str,
    confidence: str,
    evidence_note: str,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "field_name": field_name,
        "value": _jsonable(value),
        "source_table": source_table,
        "source_column": source_column,
        "confidence": confidence,
        "evidence_note": evidence_note,
    }
    payload.update({key: _jsonable(value) for key, value in extra.items() if value is not None})
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "hex") and hasattr(value, "version"):
        return str(value)
    return value


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def money(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(Decimal("0.01")))


def bool_from_count(count: int | None) -> bool:
    return bool(count and count > 0)


def payment_matches(contract_price: Decimal | None, payment_total: Decimal | None) -> bool | None:
    if contract_price is None or payment_total is None:
        return None
    return abs(contract_price - payment_total) <= Decimal("1.00")


def calculate_price_per_apartment(
    contract_price: Decimal | None,
    apartments_count: int | None,
) -> Decimal | None:
    if contract_price is None or not apartments_count:
        return None
    return (contract_price / Decimal(apartments_count)).quantize(Decimal("0.01"))


def sum_payment_schedule_amounts(items: list[dict[str, Any]]) -> Decimal | None:
    values = [
        decimal_or_none(item.get("amount_gross")) or decimal_or_none(item.get("amount_net"))
        for item in items
    ]
    present = [value for value in values if value is not None]
    return sum(present, Decimal("0")) if present else None


def determine_kg_readiness(
    text_layer_status: str,
    blocking_missing_fields: list[str],
    blocking_weak_evidence_fields: list[str],
    payment_schedule_matches_contract_price: bool | None,
) -> str:
    if text_layer_status == "fail":
        return "not_ready"
    critical = {"apartments_count", "contract_price"}
    if critical.issubset(set(blocking_missing_fields)):
        return "not_ready"
    if payment_schedule_matches_contract_price is False:
        return "needs_review"
    if blocking_missing_fields or blocking_weak_evidence_fields:
        return "needs_review"
    return "ready"


def readiness_reasons(
    text_layer_status: str,
    blocking_missing_fields: list[str],
    blocking_weak_evidence_fields: list[str],
    payment_schedule_matches_contract_price: bool | None,
    kg_readiness_status: str,
) -> list[str]:
    reasons: list[str] = []
    if text_layer_status == "fail":
        reasons.append("text_layer_status is fail")
    elif text_layer_status == "warning":
        reasons.append("text layer has warnings but not blocking failures")
    if blocking_missing_fields:
        reasons.append("blocking missing fields: " + ", ".join(blocking_missing_fields))
    if blocking_weak_evidence_fields:
        reasons.append("blocking weak evidence fields: " + ", ".join(blocking_weak_evidence_fields))
    if payment_schedule_matches_contract_price is False:
        reasons.append("payment schedule total does not match contract price")
    if not reasons and kg_readiness_status == "ready":
        reasons.append("all blocking facts have acceptable evidence")
    return reasons


def confidence_summary(missing_fields: list[str], weak_evidence_fields: list[str]) -> str:
    if not missing_fields and not weak_evidence_fields:
        return "strong"
    if len(missing_fields) <= 3 and len(weak_evidence_fields) <= 4:
        return "medium"
    return "weak"


def _fetch_one(
    conn: psycopg.Connection[Any],
    sql: str,
    params: tuple[Any, ...],
) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetch_scalar(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> Any:
    row = conn.execute(sql, params).fetchone()
    return next(iter(row.values())) if row else None


def _primary_contract(conn: psycopg.Connection[Any], project_code: str) -> dict[str, Any] | None:
    return _fetch_one(
        conn,
        """
        SELECT c.id, c.contract_code
        FROM core.contracts c
        JOIN core.projects p ON p.id = c.project_id
        WHERE p.project_code = %s
        ORDER BY CASE WHEN c.contract_code = 'raw_extracted_text' THEN 1 ELSE 0 END, c.contract_code
        LIMIT 1
        """,
        (project_code,),
    )


def _text_evidence(
    conn: psycopg.Connection[Any],
    project_code: str,
    patterns: list[str],
    field_name: str,
) -> tuple[bool, dict[str, Any] | None]:
    where = " OR ".join(["ds.body_text ILIKE %s" for _ in patterns])
    row = _fetch_one(
        conn,
        f"""
        SELECT
            ds.id AS section_id,
            dc.id AS clause_id,
            cd.document_type,
            ds.metadata->>'source_file_id' AS source_file_id
        FROM doc.sections ds
        JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
        JOIN core.contracts c ON c.id = cd.contract_id
        JOIN core.projects p ON p.id = c.project_id
        LEFT JOIN doc.clauses dc ON dc.section_id = ds.id
        WHERE p.project_code = %s AND ({where})
        ORDER BY ds.id
        LIMIT 1
        """,
        (project_code, *[f"%{pattern}%" for pattern in patterns]),
    )
    if not row:
        return False, None
    return True, evidence(
        field_name,
        True,
        "doc.sections",
        "body_text",
        "medium",
        "Text mention found in document sections.",
        section_id=row["section_id"],
        clause_id=row["clause_id"],
        document_type=row["document_type"],
        source_file_id=row["source_file_id"],
    )


def _document_type_evidence(
    conn: psycopg.Connection[Any],
    project_code: str,
    document_types: list[str],
    field_name: str,
) -> tuple[bool, dict[str, Any] | None]:
    row = _fetch_one(
        conn,
        """
        SELECT cd.id AS contract_document_id, cd.source_file_id, cd.document_type
        FROM core.contract_documents cd
        JOIN core.contracts c ON c.id = cd.contract_id
        JOIN core.projects p ON p.id = c.project_id
        WHERE p.project_code = %s
          AND cd.document_type = ANY(%s)
        ORDER BY cd.document_type
        LIMIT 1
        """,
        (project_code, document_types),
    )
    if not row:
        return False, None
    return True, evidence(
        field_name,
        True,
        "core.contract_documents",
        "document_type",
        "medium_high",
        "Relevant document type is linked to the project.",
        source_file_id=row["source_file_id"],
        document_type=row["document_type"],
        contract_document_id=row["contract_document_id"],
    )


def build_project_facts(
    conn: psycopg.Connection[Any],
    project: dict[str, Any],
    quality_by_project: dict[str, dict[str, Any]],
) -> ReferenceFacts:
    project_code = project["project_code"]
    quality = quality_by_project.get(project_code, {})
    text_layer_status = quality.get("status", "fail")
    source_coverage_status = "ok" if text_layer_status == "ok" else text_layer_status
    contract = _primary_contract(conn, project_code)
    contract_id = contract["id"] if contract else None

    facts = ReferenceFacts(
        values={
            "project_code": project_code,
            "project_display_name": project["project_name_redacted"],
            "source_coverage_status": source_coverage_status,
            "text_layer_status": text_layer_status,
        }
    )

    prop = _fetch_one(
        conn,
        """
        SELECT pr.*
        FROM core.properties pr
        JOIN core.projects p ON p.id = pr.project_id
        WHERE p.project_code = %s
        ORDER BY pr.property_code
        LIMIT 1
        """,
        (project_code,),
    )
    prop_map = {
        "apartments_count": "apartment_count",
        "buildings_count": "building_count",
        "staircases_count": "stairwell_count",
        "floors_count": "floor_count",
        "floor_area_m2": "floor_area_m2",
    }
    metadata = prop.get("metadata") if prop else {}
    for field_name, column in prop_map.items():
        value = prop.get(column) if prop else None
        facts.values[field_name] = _jsonable(value)
        if value is None:
            facts.missing_fields.append(field_name)
        else:
            facts.evidence.append(
                evidence(field_name, value, "core.properties", column, "high", "Property fact.")
            )

    business_premises_count = metadata.get("commercial_unit_count") if isinstance(metadata, dict) else None
    facts.values["business_premises_count"] = business_premises_count
    if business_premises_count is None:
        facts.missing_fields.append("business_premises_count")
    else:
        facts.evidence.append(
            evidence(
                "business_premises_count",
                business_premises_count,
                "core.properties",
                "metadata.commercial_unit_count",
                "medium_high",
                "RFQ metadata fact.",
            )
        )

    jv_verticals = metadata.get("jv_vertical_stack_count") if isinstance(metadata, dict) else None
    sv_verticals = metadata.get("sv_vertical_stack_count") if isinstance(metadata, dict) else None
    for field_name, value, note in (
        ("jv_verticals_count", jv_verticals, "JV vertical count from property metadata."),
        ("sv_verticals_count", sv_verticals, "SV vertical count from property metadata."),
    ):
        facts.values[field_name] = value
        if value is None:
            facts.missing_fields.append(field_name)
        else:
            facts.evidence.append(
                evidence(field_name, value, "core.properties", "metadata", "medium_high", note)
            )

    _add_scope(conn, contract_id, facts)
    _add_finance(conn, contract_id, project_code, facts)
    _add_availability_flags(conn, contract_id, project_code, facts)

    blocking_missing = [
        field_name for field_name in facts.missing_fields if field_name in KG_BLOCKING_MISSING_FIELDS
    ]
    blocking_weak = [
        field_name
        for field_name in facts.weak_evidence_fields
        if field_name in KG_BLOCKING_WEAK_FIELDS
    ]
    kg_readiness_status = determine_kg_readiness(
        text_layer_status,
        blocking_missing,
        blocking_weak,
        facts.values.get("payment_schedule_matches_contract_price"),
    )
    reasons = readiness_reasons(
        text_layer_status,
        blocking_missing,
        blocking_weak,
        facts.values.get("payment_schedule_matches_contract_price"),
        kg_readiness_status,
    )
    facts.values["missing_fields"] = ", ".join(facts.missing_fields)
    facts.values["weak_evidence_fields"] = ", ".join(facts.weak_evidence_fields)
    facts.values["blocking_missing_fields"] = ", ".join(blocking_missing)
    facts.values["blocking_weak_evidence_fields"] = ", ".join(blocking_weak)
    facts.values["kg_readiness_reasons"] = "; ".join(reasons)
    facts.values["confidence_summary"] = confidence_summary(
        facts.missing_fields, facts.weak_evidence_fields
    )
    facts.values["kg_readiness_status"] = kg_readiness_status
    return facts


def _add_scope(
    conn: psycopg.Connection[Any],
    contract_id: Any,
    facts: ReferenceFacts,
) -> None:
    if not contract_id:
        for field_name in ("jv_scope_summary", "sv_scope_summary", "bottom_drain_scope", "yard_line_scope"):
            facts.values[field_name] = None
            facts.missing_fields.append(field_name)
        return
    rows = conn.execute(
        """
        SELECT system_type, segment_type, segment_name, included_in_contract, boundary_text, source_clause_id
        FROM domain.sewer_segments
        WHERE contract_id = %s
        ORDER BY system_type, flow_order
        """,
        (contract_id,),
    ).fetchall()
    jv = [row for row in rows if row["system_type"] == "JV"]
    sv = [row for row in rows if row["system_type"] == "SV"]
    jv_summary = "; ".join(row["segment_name"] for row in jv) or None
    sv_summary = "; ".join(row["segment_name"] for row in sv) or None
    facts.values["jv_scope_summary"] = jv_summary
    facts.values["sv_scope_summary"] = sv_summary
    for field_name, value, system in (
        ("jv_scope_summary", jv_summary, "JV"),
        ("sv_scope_summary", sv_summary, "SV"),
    ):
        if value:
            facts.evidence.append(
                evidence(
                    field_name,
                    value,
                    "domain.sewer_segments",
                    "segment_name",
                    "medium_high",
                    f"{system} scope from sewer segment rows.",
                )
            )
        else:
            facts.missing_fields.append(field_name)

    for field_name, segment_type in (
        ("bottom_drain_scope", "base_drain"),
        ("yard_line_scope", "plot_line"),
    ):
        row = next((item for item in rows if item["segment_type"] == segment_type), None)
        value = row["boundary_text"] if row else None
        facts.values[field_name] = value
        if value:
            facts.evidence.append(
                evidence(
                    field_name,
                    value,
                    "domain.sewer_segments",
                    "boundary_text",
                    "medium_high",
                    f"{segment_type} boundary text.",
                    clause_id=row["source_clause_id"],
                )
            )
        else:
            facts.missing_fields.append(field_name)


def _add_finance(
    conn: psycopg.Connection[Any],
    contract_id: Any,
    project_code: str,
    facts: ReferenceFacts,
) -> None:
    price_row = None
    if contract_id:
        price_row = _fetch_one(
            conn,
            """
            SELECT id, amount_gross, amount_net
            FROM finance.contract_prices
            WHERE contract_id = %s AND price_type = 'fixed_contract_price'
            ORDER BY amount_gross DESC NULLS LAST, amount_net DESC NULLS LAST
            LIMIT 1
            """,
            (contract_id,),
        )
    contract_price = decimal_or_none((price_row or {}).get("amount_gross")) or decimal_or_none(
        (price_row or {}).get("amount_net")
    )
    facts.values["contract_price"] = money(contract_price)
    if contract_price is None:
        facts.missing_fields.append("contract_price")
    else:
        facts.evidence.append(
            evidence(
                "contract_price",
                contract_price,
                "finance.contract_prices",
                "amount_gross",
                "high",
                "Fixed contract price.",
                source_table_id=(price_row or {}).get("id"),
            )
        )

    payment_total = None
    if contract_id:
        payment_total = decimal_or_none(
            _fetch_scalar(
                conn,
                """
                SELECT coalesce(sum(amount_gross), sum(amount_net))
                FROM finance.payment_schedule_items
                WHERE contract_id = %s
                """,
                (contract_id,),
            )
        )
    facts.values["payment_schedule_total"] = money(payment_total)
    if payment_total is None:
        facts.missing_fields.append("payment_schedule_total")
    else:
        facts.evidence.append(
            evidence(
                "payment_schedule_total",
                payment_total,
                "finance.payment_schedule_items",
                "amount_gross",
                "high",
                "Sum of payment schedule items.",
            )
        )

    matches = payment_matches(contract_price, payment_total)
    facts.values["payment_schedule_matches_contract_price"] = matches
    if matches is None:
        facts.weak_evidence_fields.append("payment_schedule_matches_contract_price")

    apartments = facts.values.get("apartments_count")
    price_per_apartment = calculate_price_per_apartment(
        contract_price,
        int(apartments) if apartments else None,
    )
    if price_per_apartment is not None:
        facts.values["price_per_apartment"] = money(price_per_apartment)
        facts.evidence.append(
            evidence(
                "price_per_apartment",
                facts.values["price_per_apartment"],
                "computed",
                "contract_price/apartments_count",
                "high",
                "Computed from contract price and apartment count.",
            )
        )
    else:
        facts.values["price_per_apartment"] = None
        facts.missing_fields.append("price_per_apartment")

    for field_name, table_name in (
        ("unit_prices_available", "finance.unit_prices"),
        ("securities_available", "finance.securities"),
        ("insurance_available", "finance.insurances"),
    ):
        count = _fetch_scalar(conn, f"SELECT count(*) FROM {table_name} WHERE contract_id = %s", (contract_id,)) if contract_id else 0
        value = bool_from_count(count)
        facts.values[field_name] = value
        if value:
            facts.evidence.append(
                evidence(field_name, value, table_name, "count", "high", f"{count} rows found.")
            )
        else:
            document_types = {
                "unit_prices_available": ["unit_prices"],
                "securities_available": ["security_document", "warranty_security"],
                "insurance_available": ["contract_terms", "quality_manual", "quality_plan"],
            }[field_name]
            found, ev = _document_type_evidence(conn, project_code, document_types, field_name)
            facts.values[field_name] = found
            if ev:
                facts.evidence.append(ev)
                facts.weak_evidence_fields.append(field_name)
            else:
                facts.missing_fields.append(field_name)


def _add_availability_flags(
    conn: psycopg.Connection[Any],
    contract_id: Any,
    project_code: str,
    facts: ReferenceFacts,
) -> None:
    quality_count = _fetch_scalar(
        conn,
        "SELECT count(*) FROM quality.requirements WHERE contract_id = %s",
        (contract_id,),
    ) if contract_id else 0
    quality_available = bool_from_count(quality_count)
    facts.values["quality_requirements_available"] = quality_available
    if quality_available:
        facts.evidence.append(
            evidence(
                "quality_requirements_available",
                True,
                "quality.requirements",
                "count",
                "high",
                f"{quality_count} quality requirement rows found.",
            )
        )
    else:
        found, ev = _text_evidence(conn, project_code, ["laatu", "ISO 11296", "kuvataan"], "quality_requirements_available")
        facts.values["quality_requirements_available"] = found
        if ev:
            facts.evidence.append(ev)
            facts.weak_evidence_fields.append("quality_requirements_available")
        else:
            facts.missing_fields.append("quality_requirements_available")

    for field_name, patterns in (
        ("video_inspection_available", ["videotarkastus", "videon", "kuvaus"]),
        ("warranty_notes_available", ["takuu", "takuuajan"]),
    ):
        doc_types = {
            "video_inspection_available": ["video_inspection_report"],
            "warranty_notes_available": ["warranty_security", "security_document", "handover_minutes"],
        }[field_name]
        found, ev = _document_type_evidence(conn, project_code, doc_types, field_name)
        if not found:
            found, ev = _text_evidence(conn, project_code, patterns, field_name)
        facts.values[field_name] = found
        if ev:
            facts.evidence.append(ev)
            if ev["confidence"] == "medium":
                facts.weak_evidence_fields.append(field_name)
        else:
            facts.missing_fields.append(field_name)

    handover_count = _fetch_scalar(
        conn,
        "SELECT count(*) FROM ops.handover_records WHERE project_code = %s",
        (project_code,),
    )
    handover_available = bool_from_count(handover_count)
    facts.values["handover_or_reception_available"] = handover_available
    if handover_available:
        facts.evidence.append(
            evidence(
                "handover_or_reception_available",
                True,
                "ops.handover_records",
                "count",
                "high",
                f"{handover_count} handover rows found.",
            )
        )
    else:
        found, ev = _document_type_evidence(
            conn,
            project_code,
            ["handover_minutes", "financial_final_report"],
            "handover_or_reception_available",
        )
        if not found:
            found, ev = _text_evidence(
                conn,
                project_code,
                ["vastaanotto", "luovutus"],
                "handover_or_reception_available",
            )
        facts.values["handover_or_reception_available"] = found
        if ev:
            facts.evidence.append(ev)
            if ev["confidence"] == "medium":
                facts.weak_evidence_fields.append("handover_or_reception_available")
        else:
            facts.missing_fields.append("handover_or_reception_available")

    defect_count = _fetch_scalar(
        conn,
        """
        SELECT count(*)
        FROM ops.project_observations
        WHERE project_code = %s
          AND observation_type IN ('defect', 'open_item', 'quality_issue')
        """,
        (project_code,),
    )
    facts.values["defects_or_open_items_count"] = int(defect_count or 0) if defect_count else None
    if defect_count:
        facts.evidence.append(
            evidence(
                "defects_or_open_items_count",
                defect_count,
                "ops.project_observations",
                "count",
                "medium_high",
                "Operational defect/open item observations.",
            )
        )
    else:
        facts.missing_fields.append("defects_or_open_items_count")


def build_reference_facts(conn: psycopg.Connection[Any]) -> list[ReferenceFacts]:
    quality_rows = project_summary(conn)
    quality_by_project = {row["project_code"]: row for row in quality_rows}
    projects = conn.execute(
        """
        SELECT project_code, project_name_redacted
        FROM core.projects
        ORDER BY project_code
        """
    ).fetchall()
    return [build_project_facts(conn, dict(project), quality_by_project) for project in projects]


def render_markdown(facts: list[ReferenceFacts]) -> str:
    headers = FACT_FIELDS
    lines = [
        "# Reference Facts Matrix",
        "",
        "This report is a comparison and KG-readiness gate. It is generated from the existing PostgreSQL layers; it does not create a knowledge graph.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for item in facts:
        lines.append("| " + " | ".join(_md(item.values.get(field)) for field in headers) + " |")
    lines.extend(["", "## Evidence", ""])
    for item in facts:
        lines.extend(
            [
                f"### {item.values['project_code']}",
                "",
                "```json",
                json.dumps(item.evidence, ensure_ascii=False, indent=2, default=str),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _md(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_csv(path: Path, facts: list[ReferenceFacts]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*FACT_FIELDS, "evidence_json"])
        writer.writeheader()
        for item in facts:
            row = {field: _jsonable(item.values.get(field)) for field in FACT_FIELDS}
            row["evidence_json"] = json.dumps(item.evidence, ensure_ascii=False, default=str)
            writer.writerow(row)


def write_reports(output_md: Path, output_csv: Path, facts: list[ReferenceFacts]) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(facts) + "\n", encoding="utf-8")
    write_csv(output_csv, facts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    with psycopg.connect(database_url(args.db, args.env), row_factory=dict_row) as conn:
        facts = build_reference_facts(conn)
    write_reports(args.output_md, args.output_csv, facts)
    print(f"Wrote reference facts matrix to {args.output_md} and {args.output_csv}")


if __name__ == "__main__":
    main()
