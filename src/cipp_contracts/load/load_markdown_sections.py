from __future__ import annotations

import argparse
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url

PAGE_RE = re.compile(r"^## Page (\d+)\n\n(.*?)(?=^## Page \d+|\Z)", re.MULTILINE | re.DOTALL)
HEADING_RE = re.compile(r"^## (.+?)\n\n(.*?)(?=^## .+|\Z)", re.MULTILINE | re.DOTALL)
MARKDOWN_FALLBACKS = {
    "unit_prices": "contractor_offer",
    "quality_manual": "quality_plan",
}


def load_sections(project_code: str, markdown_dir: Path, db_url: str) -> int:
    inserted = 0
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cd.id, cd.document_type
                FROM core.contract_documents cd
                JOIN core.contracts c ON c.id = cd.contract_id
                JOIN core.projects p ON p.id = c.project_id
                WHERE p.project_code = %s
                """,
                (project_code,),
            )
            documents = {row["document_type"]: row["id"] for row in cur.fetchall()}

            for document_type, contract_document_id in sorted(documents.items()):
                markdown_stem = document_type
                markdown_path = markdown_dir / f"{markdown_stem}.md"
                if not markdown_path.exists() and document_type in MARKDOWN_FALLBACKS:
                    markdown_stem = MARKDOWN_FALLBACKS[document_type]
                    markdown_path = markdown_dir / f"{markdown_stem}.md"
                if not markdown_path.exists():
                    continue
                if not contract_document_id:
                    continue

                cur.execute(
                    "DELETE FROM doc.sections WHERE contract_document_id = %s",
                    (contract_document_id,),
                )

                markdown = markdown_path.read_text(encoding="utf-8")
                matches = list(PAGE_RE.finditer(markdown))
                is_page_document = bool(matches)
                if not matches:
                    matches = list(HEADING_RE.finditer(markdown))

                for order, match in enumerate(matches, start=1):
                    if is_page_document:
                        title = f"Page {int(match.group(1))}"
                        section_key = f"page_{int(match.group(1)):03d}"
                        page_no = int(match.group(1))
                    else:
                        title = match.group(1).strip()
                        section_key = f"section_{order:03d}"
                        page_no = None
                    body_text = match.group(2).strip()
                    if not body_text:
                        continue

                    cur.execute(
                        """
                        INSERT INTO doc.sections (
                            contract_document_id, section_order, section_key, title,
                            body_text, page_start, page_end, source_confidence
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                        """,
                        (
                            contract_document_id,
                            order,
                            section_key,
                            title,
                            body_text,
                            page_no,
                            page_no,
                            100,
                        ),
                    )
                    section_id = cur.fetchone()["id"]
                    cur.execute(
                        """
                        INSERT INTO doc.clauses (
                            section_id, clause_key, clause_type, title, clause_text,
                            normalized_summary, source_page
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            section_id,
                            f"{document_type}_{section_key}",
                            "page_text" if is_page_document else "legal_section",
                            f"{document_type} {title}",
                            body_text,
                            body_text[:500],
                            page_no,
                        ),
                    )
                    inserted += 1
        conn.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    inserted = load_sections(args.project, args.input, database_url(args.db, args.env))
    print(f"Loaded {inserted} markdown sections and clauses")


if __name__ == "__main__":
    main()
