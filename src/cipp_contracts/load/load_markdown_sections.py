from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url

SOURCE_PAGE_RE = re.compile(
    r"^## Source (\d+) / Page (\d+): (.+?)\n\n(.*?)(?=^## Source \d+ / Page \d+:|^## Page \d+|\Z)",
    re.MULTILINE | re.DOTALL,
)
PAGE_RE = re.compile(r"^## Page (\d+)\n\n(.*?)(?=^## Page \d+|\Z)", re.MULTILINE | re.DOTALL)
HEADING_RE = re.compile(r"^## (.+?)\n\n(.*?)(?=^## .+|\Z)", re.MULTILINE | re.DOTALL)
MARKDOWN_FALLBACKS = {
    "unit_prices": "contractor_offer",
    "quality_manual": "quality_plan",
}


def extract_inline_metadata(body_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    patterns = {
        "source_file": r"^Source file: `(.+?)`$",
        "source_file_id": r"^Source file id: `(.+?)`$",
        "extractor_name": r"^Extractor: `(.+?)`$",
        "extractor_status": r"^Extractor status: `(.+?)`$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, body_text, flags=re.MULTILINE)
        if match:
            metadata[key] = match.group(1)
    return metadata


def parse_markdown_sections(markdown: str) -> list[dict[str, Any]]:
    source_matches = list(SOURCE_PAGE_RE.finditer(markdown))
    if source_matches:
        parsed = []
        for order, match in enumerate(source_matches, start=1):
            source_order = int(match.group(1))
            page_no = int(match.group(2))
            filename = match.group(3).strip()
            body_text = match.group(4).strip()
            metadata = {"source_order": source_order, "source_filename": filename}
            metadata.update(extract_inline_metadata(body_text))
            parsed.append(
                {
                    "order": order,
                    "title": f"Source {source_order:03d} / Page {page_no:03d}: {filename}",
                    "section_key": f"source_{source_order:03d}_page_{page_no:03d}",
                    "page_no": page_no,
                    "body_text": body_text,
                    "clause_type": "extracted_page_text",
                    "metadata": metadata,
                }
            )
        return parsed

    page_matches = list(PAGE_RE.finditer(markdown))
    if page_matches:
        return [
            {
                "order": order,
                "title": f"Page {int(match.group(1))}",
                "section_key": f"page_{int(match.group(1)):03d}",
                "page_no": int(match.group(1)),
                "body_text": match.group(2).strip(),
                "clause_type": "page_text",
                "metadata": {},
            }
            for order, match in enumerate(page_matches, start=1)
        ]

    heading_matches = list(HEADING_RE.finditer(markdown))
    return [
        {
            "order": order,
            "title": match.group(1).strip(),
            "section_key": f"section_{order:03d}",
            "page_no": None,
            "body_text": match.group(2).strip(),
            "clause_type": "legal_section",
            "metadata": {},
        }
        for order, match in enumerate(heading_matches, start=1)
    ]


def ensure_contract_documents_from_raw(
    cur: psycopg.Cursor[Any],
    project_code: str,
) -> int:
    cur.execute(
        """
        SELECT id
        FROM core.projects
        WHERE project_code = %s
        """,
        (project_code,),
    )
    project = cur.fetchone()
    if not project:
        return 0

    cur.execute(
        """
        INSERT INTO core.contracts (
            project_id, contract_code, subject, metadata
        )
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (project_id, contract_code) DO UPDATE
        SET metadata = core.contracts.metadata || EXCLUDED.metadata
        RETURNING id
        """,
        (
            project["id"],
            "raw_extracted_text",
            "Raw extracted document text layer",
            Jsonb({"created_by": "load_markdown_sections", "source": "raw.source_files"}),
        ),
    )
    contract_id = cur.fetchone()["id"]

    cur.execute(
        """
        WITH raw_documents AS (
            SELECT
                sf.document_type,
                min(sf.id::text)::uuid AS source_file_id,
                sum(coalesce(sf.page_count, 0))::integer AS page_count
            FROM raw.source_files sf
            WHERE sf.project_code = %s
            GROUP BY sf.document_type
        )
        INSERT INTO core.contract_documents (
            contract_id, source_file_id, document_type, document_title_redacted,
            page_count, precedence_rank, is_contract_document, metadata
        )
        SELECT
            %s,
            rd.source_file_id,
            rd.document_type,
            rd.document_type,
            nullif(rd.page_count, 0),
            99,
            false,
            %s
        FROM raw_documents rd
        ON CONFLICT (contract_id, document_type, (coalesce(attachment_no, ''))) DO UPDATE
        SET source_file_id = coalesce(core.contract_documents.source_file_id, EXCLUDED.source_file_id),
            page_count = coalesce(core.contract_documents.page_count, EXCLUDED.page_count),
            metadata = core.contract_documents.metadata || EXCLUDED.metadata
        """,
        (
            project_code,
            contract_id,
            Jsonb({"created_by": "load_markdown_sections", "source": "raw.source_files"}),
        ),
    )
    return cur.rowcount


def load_sections(
    project_code: str,
    markdown_dir: Path,
    db_url: str,
    ensure_raw_documents: bool = False,
    prune_missing_markdown: bool = False,
) -> int:
    inserted = 0
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if ensure_raw_documents:
                ensure_contract_documents_from_raw(cur, project_code)
            if prune_missing_markdown:
                cur.execute(
                    """
                    DELETE FROM doc.sections ds
                    USING core.contract_documents cd,
                          core.contracts c,
                          core.projects p
                    WHERE ds.contract_document_id = cd.id
                      AND cd.contract_id = c.id
                      AND c.project_id = p.id
                      AND p.project_code = %s
                    """,
                    (project_code,),
                )
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
                    if prune_missing_markdown:
                        cur.execute(
                            "DELETE FROM doc.sections WHERE contract_document_id = %s",
                            (contract_document_id,),
                        )
                    continue
                if not contract_document_id:
                    continue

                cur.execute(
                    "DELETE FROM doc.sections WHERE contract_document_id = %s",
                    (contract_document_id,),
                )

                markdown = markdown_path.read_text(encoding="utf-8")
                sections = parse_markdown_sections(markdown)

                for section in sections:
                    body_text = section["body_text"]
                    if not body_text:
                        continue

                    cur.execute(
                        """
                        INSERT INTO doc.sections (
                            contract_document_id, section_order, section_key, title,
                            body_text, page_start, page_end, source_confidence, metadata
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                        """,
                        (
                            contract_document_id,
                            section["order"],
                            section["section_key"],
                            section["title"],
                            body_text,
                            section["page_no"],
                            section["page_no"],
                            100,
                            Jsonb(section["metadata"]),
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
                            f"{document_type}_{section['section_key']}",
                            section["clause_type"],
                            f"{document_type} {section['title']}",
                            body_text,
                            body_text[:500],
                            section["page_no"],
                        ),
                    )
                    inserted += 1
        conn.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--ensure-raw-documents", action="store_true")
    parser.add_argument("--prune-missing-markdown", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    inserted = load_sections(
        args.project,
        args.input,
        database_url(args.db, args.env),
        ensure_raw_documents=args.ensure_raw_documents,
        prune_missing_markdown=args.prune_missing_markdown,
    )
    print(f"Loaded {inserted} markdown sections and clauses")


if __name__ == "__main__":
    main()
