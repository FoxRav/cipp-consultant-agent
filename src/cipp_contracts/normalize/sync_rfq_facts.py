from __future__ import annotations

import argparse
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url
from cipp_contracts.normalize.build_project_canonical import PROJECT_NAMES
from cipp_contracts.normalize.rfq_facts import parse_rfq_property_facts


def sync_project(project_code: str, markdown_dir: Path, db_url: str) -> None:
    rfq_path = markdown_dir / "rfq.md"
    if not rfq_path.exists():
        raise FileNotFoundError(f"RFQ markdown missing: {rfq_path}")
    label = PROJECT_NAMES.get(project_code, project_code)
    facts = parse_rfq_property_facts(label, rfq_path.read_text(encoding="utf-8"))

    with psycopg.connect(db_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, c.id, pr.property_code
                FROM core.projects p
                JOIN core.contracts c ON c.project_id = p.id
                LEFT JOIN core.properties pr ON pr.project_id = p.id
                WHERE p.project_code = %s
                LIMIT 1
                """,
                (project_code,),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"Project not found in database: {project_code}")
            project_id, contract_id, property_code = row
            cur.execute(
                """
                INSERT INTO core.properties (
                    project_id, property_code, city_redacted, building_year, building_count,
                    stairwell_count, apartment_count, floor_area_m2, floor_count, metadata
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (project_id, property_code) DO UPDATE
                SET building_year = EXCLUDED.building_year,
                    building_count = EXCLUDED.building_count,
                    stairwell_count = EXCLUDED.stairwell_count,
                    apartment_count = EXCLUDED.apartment_count,
                    floor_area_m2 = EXCLUDED.floor_area_m2,
                    floor_count = EXCLUDED.floor_count,
                    metadata = core.properties.metadata || EXCLUDED.metadata
                """,
                (
                    project_id,
                    property_code or f"property_{project_code}",
                    "Kaupunki1",
                    facts.building_year,
                    facts.building_count,
                    facts.stairwell_count,
                    facts.apartment_count,
                    facts.floor_area_m2,
                    facts.floor_count,
                    Jsonb(facts.metadata),
                ),
            )
            vertical_count = facts.metadata.get("jv_vertical_stack_count")
            if vertical_count:
                cur.execute(
                    """
                    DELETE FROM domain.scope_items
                    WHERE contract_id = %s AND item_code = 'scope_jv_verticals'
                    """,
                    (contract_id,),
                )
                cur.execute(
                    """
                    INSERT INTO domain.scope_items (
                        contract_id, item_code, system_type, item_name,
                        included_in_contract, is_option, is_extra_work, notes
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        contract_id,
                        "scope_jv_verticals",
                        "JV",
                        f"{vertical_count} JV-pystylinjaa",
                        True,
                        False,
                        False,
                        facts.metadata.get("source_quote"),
                    ),
                )
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", action="append", required=True)
    parser.add_argument("--extracted-root", type=Path, default=Path("data/extracted"))
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    db_url = database_url(args.db, args.env)
    for project_code in args.project:
        sync_project(project_code, args.extracted_root / project_code / "markdown", db_url)
        print(f"Synced RFQ facts for {project_code}")


if __name__ == "__main__":
    main()
