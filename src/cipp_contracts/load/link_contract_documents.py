from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

from cipp_contracts.config import database_url


def link_documents(project_code: str, db_url: str) -> int:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH candidates AS (
                    SELECT
                        cd.id AS contract_document_id,
                        sf.id AS source_file_id,
                        sf.page_count,
                        row_number() OVER (
                            PARTITION BY cd.id
                            ORDER BY CASE WHEN sf.project_code = p.project_code THEN 0 ELSE 1 END
                        ) AS rn
                    FROM core.contract_documents cd
                    JOIN core.contracts c ON c.id = cd.contract_id
                    JOIN core.projects p ON p.id = c.project_id
                    JOIN raw.source_file_document_types mapping
                      ON mapping.document_type = cd.document_type
                    JOIN raw.source_files sf
                      ON sf.id = mapping.source_file_id
                    WHERE p.project_code = %s
                      AND (
                          sf.project_code = p.project_code
                          OR mapping.document_type IN (
                              'law_alueidenkayttolaki_132_1999',
                              'law_rakentamislaki_751_2023',
                              'yse_1998'
                          )
                      )
                )
                UPDATE core.contract_documents cd
                SET source_file_id = candidates.source_file_id,
                    page_count = candidates.page_count
                FROM candidates
                WHERE candidates.contract_document_id = cd.id
                  AND candidates.rn = 1
                """,
                (project_code,),
            )
            updated = cur.rowcount
        conn.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    updated = link_documents(args.project, database_url(args.db, args.env))
    print(f"Linked {updated} contract document rows")


if __name__ == "__main__":
    main()
