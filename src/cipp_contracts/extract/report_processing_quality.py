from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def fetch_rows(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return list(conn.execute(sql, params).fetchall())


def evaluate_project_status(row: dict[str, Any]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    source_files_total = int(row.get("source_files_total") or 0)
    raw_pages_count = int(row.get("raw_pages_count") or 0)
    doc_sections_count = int(row.get("doc_sections_count") or 0)
    source_files_without_status = int(row.get("source_files_without_text_or_status") or 0)
    latest_failed = int(row.get("latest_failed_extraction_runs") or 0)

    if source_files_total == 0:
        return "fail", ["no source files"]
    if raw_pages_count == 0:
        return "fail", ["no raw page/text records"]
    if doc_sections_count == 0:
        return "fail", ["no doc.sections records"]
    if source_files_without_status:
        return "fail", [f"{source_files_without_status} source files without text or latest status"]

    if latest_failed:
        warnings.append(f"{latest_failed} latest failed extraction runs")
    if int(row.get("markdown_documents_count") or 0) == 0:
        warnings.append("no markdown-backed document sections")
    if int(row.get("source_files_with_raw_pages") or 0) < source_files_total:
        warnings.append("some source files rely on status/metadata instead of raw text")

    return ("warning" if warnings else "ok"), warnings


def project_summary(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    rows = fetch_rows(
        conn,
        """
        WITH page_counts AS (
            SELECT source_file_id, count(*) AS pages
            FROM raw.pages
            GROUP BY source_file_id
        ),
        latest_runs AS (
            SELECT *
            FROM (
                SELECT
                    source_file_id,
                    extractor_name,
                    status,
                    row_number() OVER (
                        PARTITION BY source_file_id, extractor_name
                        ORDER BY extraction_started_at DESC, id DESC
                    ) AS rn
                FROM raw.extraction_runs
            ) ranked
            WHERE rn = 1
        ),
        latest_by_file AS (
            SELECT *
            FROM (
                SELECT
                    source_file_id,
                    status,
                    row_number() OVER (
                        PARTITION BY source_file_id
                        ORDER BY extraction_started_at DESC, id DESC
                    ) AS rn
                FROM raw.extraction_runs
            ) ranked
            WHERE rn = 1
        ),
        source_status AS (
            SELECT
                sf.id,
                sf.project_code,
                sf.notes,
                coalesce(pc.pages, 0) AS pages,
                lbf.source_file_id IS NOT NULL AS has_latest_status,
                count(*) FILTER (
                    WHERE lr.extractor_name = 'office_ooxml_text' AND lr.status = 'completed'
                ) > 0 AS office_completed,
                count(*) FILTER (
                    WHERE lr.extractor_name = 'doclayout_ai_visual_ocr' AND lr.status = 'completed'
                ) > 0 AS ocr_completed,
                count(*) FILTER (
                    WHERE lr.extractor_name = 'remaining_file_text' AND lr.status = 'completed'
                ) > 0 AS remaining_completed,
                count(*) FILTER (WHERE lr.status = 'failed') AS latest_failed_runs
            FROM raw.source_files sf
            LEFT JOIN page_counts pc ON pc.source_file_id = sf.id
            LEFT JOIN latest_runs lr ON lr.source_file_id = sf.id
            LEFT JOIN latest_by_file lbf ON lbf.source_file_id = sf.id
            GROUP BY sf.id, sf.project_code, sf.notes, pc.pages, lbf.source_file_id
        ),
        section_counts AS (
            SELECT
                p.project_code,
                count(DISTINCT cd.id) FILTER (WHERE ds.id IS NOT NULL) AS markdown_documents_count,
                count(DISTINCT ds.id) AS doc_sections_count,
                count(DISTINCT dc.id) AS doc_clauses_count
            FROM core.projects p
            LEFT JOIN core.contracts c ON c.project_id = p.id
            LEFT JOIN core.contract_documents cd ON cd.contract_id = c.id
            LEFT JOIN doc.sections ds ON ds.contract_document_id = cd.id
            LEFT JOIN doc.clauses dc ON dc.section_id = ds.id
            GROUP BY p.project_code
        )
        SELECT
            ss.project_code,
            count(*) AS source_files_total,
            count(*) FILTER (WHERE ss.pages > 0) AS source_files_with_raw_pages,
            coalesce(sum(ss.pages), 0) AS raw_pages_count,
            coalesce(max(sc.markdown_documents_count), 0) AS markdown_documents_count,
            coalesce(max(sc.doc_sections_count), 0) AS doc_sections_count,
            coalesce(max(sc.doc_clauses_count), 0) AS doc_clauses_count,
            count(*) FILTER (WHERE ss.office_completed) AS office_extracted_count,
            count(*) FILTER (WHERE ss.ocr_completed) AS ocr_extracted_count,
            count(*) FILTER (
                WHERE ss.notes ILIKE 'Derived PDF converted from DWG%%'
            ) AS dwg_derived_count,
            count(*) FILTER (WHERE ss.remaining_completed) AS remaining_text_extracted_count,
            count(*) FILTER (WHERE ss.pages = 0 AND NOT ss.has_latest_status)
                AS source_files_without_text_or_status,
            coalesce(sum(ss.latest_failed_runs), 0) AS latest_failed_extraction_runs
        FROM source_status ss
        LEFT JOIN section_counts sc ON sc.project_code = ss.project_code
        GROUP BY ss.project_code
        ORDER BY ss.project_code
        """,
    )
    for row in rows:
        status, warnings = evaluate_project_status(row)
        row["status"] = status
        row["warnings"] = "; ".join(warnings)
    return rows


def extension_summary(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    return fetch_rows(
        conn,
        """
        SELECT
            project_code,
            lower(case when file_ext like '.%%' then file_ext else '.' || file_ext end) AS ext,
            count(*) AS files
        FROM raw.source_files
        GROUP BY project_code, ext
        ORDER BY project_code, ext
        """,
    )


def latest_extractor_summary(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    return fetch_rows(
        conn,
        """
        WITH latest AS (
            SELECT
                extractor_name,
                status,
                row_number() OVER (
                    PARTITION BY source_file_id, extractor_name
                    ORDER BY extraction_started_at DESC, id DESC
                ) AS rn
            FROM raw.extraction_runs
        )
        SELECT extractor_name, status, count(*) AS runs
        FROM latest
        WHERE rn = 1
        GROUP BY extractor_name, status
        ORDER BY extractor_name, status
        """,
    )


def followups(conn: psycopg.Connection[Any], limit: int) -> list[dict[str, Any]]:
    return fetch_rows(
        conn,
        """
        WITH page_counts AS (
            SELECT source_file_id, count(*) AS pages
            FROM raw.pages
            GROUP BY source_file_id
        ),
        latest AS (
            SELECT
                source_file_id,
                extractor_name,
                status,
                error_message,
                row_number() OVER (
                    PARTITION BY source_file_id, extractor_name
                    ORDER BY extraction_started_at DESC, id DESC
                ) AS rn
            FROM raw.extraction_runs
        ),
        latest_failures AS (
            SELECT
                source_file_id,
                string_agg(extractor_name || ': ' || coalesce(error_message, status), '; ') AS failures
            FROM latest
            WHERE rn = 1 AND status = 'failed'
            GROUP BY source_file_id
        )
        SELECT
            sf.project_code,
            sf.original_filename,
            sf.file_ext,
            coalesce(pc.pages, 0) AS pages,
            sf.needs_ocr,
            lf.failures
        FROM raw.source_files sf
        LEFT JOIN page_counts pc ON pc.source_file_id = sf.id
        LEFT JOIN latest_failures lf ON lf.source_file_id = sf.id
        WHERE coalesce(pc.pages, 0) = 0 OR lf.failures IS NOT NULL
        ORDER BY sf.project_code, sf.original_filename
        LIMIT %s
        """,
        (limit,),
    )


def build_report(db_url: str, limit: int) -> str:
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        projects = project_summary(conn)
        extensions = extension_summary(conn)
        extractors = latest_extractor_summary(conn)
        items = followups(conn, limit)

    total_sources = sum(int(row["source_files_total"]) for row in projects)
    total_pages = sum(int(row["raw_pages_count"]) for row in projects)
    total_followups = sum(int(row["source_files_without_text_or_status"]) for row in projects)

    lines = [
        "# Processing Quality Report",
        "",
        "## Summary",
        "",
        f"- Projects: {len(projects)}",
        f"- Source files: {total_sources}",
        f"- Raw page/text records: {total_pages}",
        f"- Source files without text or latest status: {total_followups}",
        "",
        "## Projects",
        "",
    ]
    lines.extend(
        table(
            [
                "Project",
                "source_files_total",
                "source_files_with_raw_pages",
                "raw_pages_count",
                "markdown_documents_count",
                "doc_sections_count",
                "doc_clauses_count",
                "office_extracted_count",
                "ocr_extracted_count",
                "dwg_derived_count",
                "remaining_text_extracted_count",
                "source_files_without_text_or_status",
                "latest_failed_extraction_runs",
                "warnings",
                "status",
            ],
            [
                [
                    row["project_code"],
                    row["source_files_total"],
                    row["source_files_with_raw_pages"],
                    row["raw_pages_count"],
                    row["markdown_documents_count"],
                    row["doc_sections_count"],
                    row["doc_clauses_count"],
                    row["office_extracted_count"],
                    row["ocr_extracted_count"],
                    row["dwg_derived_count"],
                    row["remaining_text_extracted_count"],
                    row["source_files_without_text_or_status"],
                    row["latest_failed_extraction_runs"],
                    row["warnings"],
                    row["status"],
                ]
                for row in projects
            ],
        )
    )

    lines.extend(["", "## Latest Extractor Status", ""])
    lines.extend(
        table(
            ["Extractor", "Status", "Files"],
            [[row["extractor_name"], row["status"], row["runs"]] for row in extractors],
        )
    )

    grouped_exts: dict[str, list[str]] = defaultdict(list)
    for row in extensions:
        grouped_exts[row["project_code"]].append(f"{row['ext']}={row['files']}")
    lines.extend(["", "## File Types By Project", ""])
    lines.extend(
        table(
            ["Project", "File types"],
            [[project, ", ".join(parts)] for project, parts in grouped_exts.items()],
        )
    )

    lines.extend(["", f"## Follow-Up Candidates (first {limit})", ""])
    if items:
        lines.extend(
            table(
                ["Project", "Filename", "Ext", "Pages", "Needs OCR", "Latest failure"],
                [
                    [
                        row["project_code"],
                        row["original_filename"],
                        row["file_ext"],
                        row["pages"],
                        row["needs_ocr"],
                        row["failures"] or "",
                    ]
                    for row in items
                ],
            )
        )
    else:
        lines.append("No follow-up candidates found.")

    lines.extend(
        [
            "",
            "## Reading The Report",
            "",
            "- Latest extractor status is based on the newest run per source file and extractor.",
            "- Historical failed runs are kept in the database as audit history.",
            "- Files without text are not always errors: images, DWG originals, ZIPs and metadata files can be valid follow-up items.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    report = build_report(database_url(args.db, args.env), args.limit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"Wrote processing quality report to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
