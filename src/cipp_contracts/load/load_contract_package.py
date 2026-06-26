from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from cipp_contracts.jsonio import read_json


def load(data: dict[str, Any], database_url: str) -> None:
    canonical_bytes = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    canonical_hash = hashlib.sha256(canonical_bytes).hexdigest()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            project_id = _upsert_project(cur, data)
            contract_id = _upsert_contract(cur, project_id, data)
            _upsert_property(cur, project_id, data)
            _upsert_parties(cur, contract_id, data)
            _upsert_documents(cur, contract_id, data)
            document_ids = _document_ids(cur, contract_id)
            _load_finance(cur, contract_id, document_ids, data)
            _load_domain(cur, contract_id, data)
            _load_quality(cur, contract_id, data)
            _insert_canonical_version(cur, project_id, contract_id, data, canonical_hash)
        conn.commit()


def _upsert_project(cur: psycopg.Cursor, data: dict[str, Any]) -> str:
    cur.execute(
        """
        INSERT INTO core.projects (project_code, project_name_redacted, project_type)
        VALUES (%s, %s, %s)
        ON CONFLICT (project_code) DO UPDATE
        SET project_name_redacted = EXCLUDED.project_name_redacted,
            project_type = EXCLUDED.project_type
        RETURNING id
        """,
        (
            data["project_code"],
            data.get("project_name_redacted", data["project_code"]),
            data.get("project_type", "cipp_sukitusurakka"),
        ),
    )
    return cur.fetchone()[0]


def _upsert_property(cur: psycopg.Cursor, project_id: str, data: dict[str, Any]) -> None:
    prop = data.get("property") or {}
    cur.execute(
        """
        INSERT INTO core.properties (
            project_id, property_code, city_redacted, building_year, building_count,
            stairwell_count, apartment_count, floor_area_m2, floor_count
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (project_id, property_code) DO UPDATE
        SET city_redacted = EXCLUDED.city_redacted,
            building_year = EXCLUDED.building_year,
            building_count = EXCLUDED.building_count,
            stairwell_count = EXCLUDED.stairwell_count,
            apartment_count = EXCLUDED.apartment_count,
            floor_area_m2 = EXCLUDED.floor_area_m2,
            floor_count = EXCLUDED.floor_count
        """,
        (
            project_id,
            prop.get("property_code", "property_001"),
            prop.get("city_redacted"),
            prop.get("building_year"),
            prop.get("building_count"),
            prop.get("stairwell_count"),
            prop.get("apartment_count"),
            prop.get("floor_area_m2"),
            prop.get("floor_count"),
        ),
    )


def _upsert_contract(cur: psycopg.Cursor, project_id: str, data: dict[str, Any]) -> str:
    contract = data.get("contract") or {}
    cur.execute(
        """
        INSERT INTO core.contracts (
            project_id, contract_code, contract_type, contract_date, revision,
            subject, standard_terms, currency_code
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (project_id, contract_code) DO UPDATE
        SET contract_type = EXCLUDED.contract_type,
            contract_date = EXCLUDED.contract_date,
            revision = EXCLUDED.revision,
            subject = EXCLUDED.subject,
            standard_terms = EXCLUDED.standard_terms,
            currency_code = EXCLUDED.currency_code
        RETURNING id
        """,
        (
            project_id,
            contract.get("contract_code", "contract_001"),
            contract.get("contract_type", "construction_contract"),
            contract.get("contract_date"),
            contract.get("revision"),
            contract.get("subject"),
            contract.get("standard_terms"),
            contract.get("currency_code", "EUR"),
        ),
    )
    return cur.fetchone()[0]


def _upsert_parties(cur: psycopg.Cursor, contract_id: str, data: dict[str, Any]) -> None:
    for party in data.get("parties") or []:
        cur.execute(
            """
            INSERT INTO core.parties (party_code, party_type, display_name_redacted, original_name_hash)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (party_code) DO UPDATE
            SET party_type = EXCLUDED.party_type,
                display_name_redacted = EXCLUDED.display_name_redacted,
                original_name_hash = EXCLUDED.original_name_hash
            RETURNING id
            """,
            (
                party["party_code"],
                party.get("party_type", "other"),
                party["display_name_redacted"],
                party.get("original_name_hash"),
            ),
        )
        party_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO core.contract_parties (contract_id, party_id, role)
            VALUES (%s,%s,%s)
            ON CONFLICT (contract_id, party_id, role) DO NOTHING
            """,
            (contract_id, party_id, party["role"]),
        )


def _upsert_documents(cur: psycopg.Cursor, contract_id: str, data: dict[str, Any]) -> None:
    cur.execute("DELETE FROM core.contract_documents WHERE contract_id = %s", (contract_id,))
    for document in data.get("documents") or []:
        title = document.get("document_title_redacted") or document["document_type"]
        cur.execute(
            """
            INSERT INTO core.contract_documents (
                contract_id, document_type, document_title_redacted, attachment_no,
                document_date, revision, page_count, precedence_rank
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (contract_id, document_type, (coalesce(attachment_no, ''))) DO UPDATE
            SET document_title_redacted = EXCLUDED.document_title_redacted,
                document_date = EXCLUDED.document_date,
                revision = EXCLUDED.revision,
                page_count = EXCLUDED.page_count,
                precedence_rank = EXCLUDED.precedence_rank
            """,
            (
                contract_id,
                document["document_type"],
                title,
                document.get("attachment_no"),
                document.get("document_date"),
                document.get("revision"),
                document.get("page_count"),
                document.get("precedence_rank"),
            ),
        )


def _document_ids(cur: psycopg.Cursor, contract_id: str) -> dict[str, str]:
    cur.execute(
        """
        SELECT document_type, id
        FROM core.contract_documents
        WHERE contract_id = %s
        """,
        (contract_id,),
    )
    return {document_type: document_id for document_type, document_id in cur.fetchall()}


def _load_finance(
    cur: psycopg.Cursor,
    contract_id: str,
    document_ids: dict[str, str],
    data: dict[str, Any],
) -> None:
    for table in (
        "finance.contract_prices",
        "finance.payment_schedule_items",
        "finance.unit_prices",
        "finance.securities",
        "finance.insurances",
        "finance.penalties",
    ):
        cur.execute(f"DELETE FROM {table} WHERE contract_id = %s", (contract_id,))

    for price in data.get("prices") or []:
        cur.execute(
            """
            INSERT INTO finance.contract_prices (
                contract_id, price_type, amount_net, vat_rate, vat_amount,
                amount_gross, currency_code, price_text
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                price["price_type"],
                price.get("amount_net"),
                price.get("vat_rate"),
                price.get("vat_amount"),
                price.get("amount_gross"),
                price.get("currency_code", "EUR"),
                price.get("price_text"),
            ),
        )

    for item in data.get("payment_schedule") or []:
        cur.execute(
            """
            INSERT INTO finance.payment_schedule_items (
                contract_id, item_no, amount_net, vat_rate, vat_amount,
                amount_gross, payment_condition, source_document_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                item["item_no"],
                item["amount_net"],
                item.get("vat_rate"),
                item.get("vat_amount"),
                item.get("amount_gross"),
                item["payment_condition"],
                document_ids.get(item.get("source_document_type")),
            ),
        )

    for unit_price in data.get("unit_prices") or []:
        cur.execute(
            """
            INSERT INTO finance.unit_prices (
                contract_id, unit_price_code, item_name, unit, amount_gross,
                amount_net, vat_rate, condition_text
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                unit_price["unit_price_code"],
                unit_price["item_name"],
                unit_price.get("unit"),
                unit_price.get("amount_gross"),
                unit_price.get("amount_net"),
                unit_price.get("vat_rate"),
                unit_price.get("condition_text"),
            ),
        )

    for security in data.get("securities") or []:
        cur.execute(
            """
            INSERT INTO finance.securities (
                contract_id, security_type, amount, amount_percent, basis,
                validity_text, issuer_role, beneficiary_role
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                security["security_type"],
                security.get("amount"),
                security.get("amount_percent"),
                security.get("basis"),
                security.get("validity_text"),
                security.get("issuer_role"),
                security.get("beneficiary_role"),
            ),
        )

    for insurance in data.get("insurances") or []:
        cur.execute(
            """
            INSERT INTO finance.insurances (
                contract_id, insurance_type, required_by_role, coverage_amount, coverage_text
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                insurance["insurance_type"],
                insurance.get("required_by_role"),
                insurance.get("coverage_amount"),
                insurance.get("coverage_text"),
            ),
        )

    for penalty in data.get("penalties") or []:
        cur.execute(
            """
            INSERT INTO finance.penalties (
                contract_id, penalty_type, percent_per_workday, max_workdays,
                basis, calculation_text
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                penalty["penalty_type"],
                penalty.get("percent_per_workday"),
                penalty.get("max_workdays"),
                penalty.get("basis"),
                penalty.get("calculation_text"),
            ),
        )


def _load_domain(cur: psycopg.Cursor, contract_id: str, data: dict[str, Any]) -> None:
    for table in (
        "domain.scope_items",
        "domain.contract_boundaries",
        "domain.technical_requirements",
        "domain.responsibility_matrix",
        "domain.schedule_milestones",
        "domain.sewer_segments",
    ):
        cur.execute(f"DELETE FROM {table} WHERE contract_id = %s", (contract_id,))

    for item in data.get("scope_items") or []:
        cur.execute(
            """
            INSERT INTO domain.scope_items (
                contract_id, item_code, system_type, item_name, included_in_contract,
                is_option, is_extra_work, notes
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                item["item_code"],
                item["system_type"],
                item["item_name"],
                item["included_in_contract"],
                item.get("is_option", False),
                item.get("is_extra_work", False),
                item.get("notes"),
            ),
        )

    for boundary in data.get("boundaries") or []:
        cur.execute(
            """
            INSERT INTO domain.contract_boundaries (
                contract_id, system_type, upstream_boundary, downstream_boundary, inspected
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                boundary["system_type"],
                boundary.get("upstream_boundary"),
                boundary.get("downstream_boundary"),
                boundary.get("inspected"),
            ),
        )

    for requirement in data.get("technical_requirements") or []:
        cur.execute(
            """
            INSERT INTO domain.technical_requirements (
                contract_id, requirement_code, requirement_type, requirement_text,
                numeric_limit, unit, standard_ref, applies_to
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                requirement["requirement_code"],
                requirement["requirement_type"],
                requirement["requirement_text"],
                requirement.get("numeric_limit"),
                requirement.get("unit"),
                requirement.get("standard_ref"),
                requirement.get("applies_to"),
            ),
        )

    for responsibility in data.get("responsibilities") or []:
        cur.execute(
            """
            INSERT INTO domain.responsibility_matrix (
                contract_id, responsibility_key, responsibility_area, responsible_role, details
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                responsibility["responsibility_key"],
                responsibility["responsibility_area"],
                responsibility["responsible_role"],
                responsibility.get("details"),
            ),
        )

    for milestone in data.get("schedule_milestones") or []:
        cur.execute(
            """
            INSERT INTO domain.schedule_milestones (
                contract_id, milestone_key, milestone_name, planned_date,
                planned_start, planned_finish, qualifier
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                milestone["milestone_key"],
                milestone["milestone_name"],
                milestone.get("planned_date"),
                milestone.get("planned_start"),
                milestone.get("planned_finish"),
                milestone.get("qualifier"),
            ),
        )

    for segment in data.get("sewer_segments") or []:
        cur.execute(
            """
            INSERT INTO domain.sewer_segments (
                contract_id, system_type, segment_type, flow_order, segment_name,
                included_in_contract, inclusion_confidence, boundary_text,
                pricing_impact, source_document_type, notes
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                segment["system_type"],
                segment["segment_type"],
                segment["flow_order"],
                segment["segment_name"],
                segment.get("included_in_contract"),
                segment.get("inclusion_confidence"),
                segment.get("boundary_text"),
                segment.get("pricing_impact"),
                segment.get("source_document_type"),
                segment.get("notes"),
            ),
        )


def _load_quality(cur: psycopg.Cursor, contract_id: str, data: dict[str, Any]) -> None:
    for table in ("quality.requirements", "quality.deliverables"):
        cur.execute(f"DELETE FROM {table} WHERE contract_id = %s", (contract_id,))

    for requirement in data.get("quality_requirements") or []:
        cur.execute(
            """
            INSERT INTO quality.requirements (
                contract_id, requirement_key, requirement_category, requirement_text,
                acceptance_criteria, evidence_required
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                requirement["requirement_key"],
                requirement["requirement_category"],
                requirement["requirement_text"],
                requirement.get("acceptance_criteria"),
                requirement.get("evidence_required"),
            ),
        )

    for deliverable in data.get("deliverables") or []:
        cur.execute(
            """
            INSERT INTO quality.deliverables (
                contract_id, deliverable_key, deliverable_name, required_at, required_by_role
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                contract_id,
                deliverable["deliverable_key"],
                deliverable["deliverable_name"],
                deliverable.get("required_at"),
                deliverable.get("required_by_role"),
            ),
        )


def _insert_canonical_version(
    cur: psycopg.Cursor,
    project_id: str,
    contract_id: str,
    data: dict[str, Any],
    canonical_hash: str,
) -> None:
    cur.execute(
        """
        SELECT coalesce(max(version_no), 0) + 1
        FROM core.canonical_contract_versions
        WHERE contract_id = %s
        """,
        (contract_id,),
    )
    version_no = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO core.canonical_contract_versions (
            project_id, contract_id, version_no, canonical_json, canonical_hash, validation_status
        )
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (project_id, contract_id, version_no, Jsonb(data), canonical_hash, "created"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    load(read_json(args.input), args.db)
    print(f"Loaded contract package from {args.input}")


if __name__ == "__main__":
    main()
