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


def project_summary(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    return fetch_rows(
        conn,
        """
        WITH page_counts AS (
            SELECT source_file_id, count(*) AS pages
            FROM raw.pages
            GROUP BY source_file_id
        ),
        latest_ocr AS (
            SELECT source_file_id, status
            FROM (
                SELECT
                    source_file_id,
                    status,
                    row_number() OVER (
                        PARTITION BY source_file_id
                        ORDER BY extraction_started_at DESC, id DESC
                    ) AS rn
                FROM raw.extraction_runs
                WHERE extractor_name = 'doclayout_ai_visual_ocr'
            ) ranked
            WHERE rn = 1
        ),
        latest_source_failures AS (
            SELECT DISTINCT source_file_id
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
            WHERE rn = 1 AND status = 'failed'
        )
        SELECT
            sf.project_code,
            count(*) AS source_files,
            count(*) FILTER (WHERE coalesce(pc.pages, 0) > 0) AS files_with_pages,
            count(*) FILTER (WHERE coalesce(pc.pages, 0) = 0) AS files_without_pages,
            coalesce(sum(pc.pages), 0) AS raw_pages,
            count(*) FILTER (WHERE sf.needs_ocr IS TRUE) AS needs_ocr,
            count(*) FILTER (
                WHERE sf.needs_ocr IS TRUE
                  AND coalesce(lo.status, '') <> 'completed'
            ) AS open_ocr,
            count(lsf.source_file_id) AS latest_failed_files
        FROM raw.source_files sf
        LEFT JOIN page_counts pc ON pc.source_file_id = sf.id
        LEFT JOIN latest_ocr lo ON lo.source_file_id = sf.id
        LEFT JOIN latest_source_failures lsf ON lsf.source_file_id = sf.id
        GROUP BY sf.project_code
        ORDER BY sf.project_code
        """,
    )


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

    total_sources = sum(int(row["source_files"]) for row in projects)
    total_pages = sum(int(row["raw_pages"]) for row in projects)
    total_followups = sum(int(row["files_without_pages"]) for row in projects)

    lines = [
        "# Processing Quality Report",
        "",
        "## Summary",
        "",
        f"- Projects: {len(projects)}",
        f"- Source files: {total_sources}",
        f"- Raw page/text records: {total_pages}",
        f"- Files without page/text records: {total_followups}",
        "",
        "## Projects",
        "",
    ]
    lines.extend(
        table(
            [
                "Project",
                "Sources",
                "Files with text",
                "Files without text",
                "Raw pages",
                "Needs OCR",
                "Open OCR",
                "Latest failed files",
            ],
            [
                [
                    row["project_code"],
                    row["source_files"],
                    row["files_with_pages"],
                    row["files_without_pages"],
                    row["raw_pages"],
                    row["needs_ocr"],
                    row["open_ocr"],
                    row["latest_failed_files"],
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
            "- Needs OCR is the original source-file flag; Open OCR means no completed visual OCR run exists yet.",
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
