from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pypdf import PdfReader

from cipp_contracts.config import database_url


def text_quality_score(text: str | None) -> float:
    if not text:
        return 0.0
    stripped = text.strip()
    if not stripped:
        return 0.0
    printable = sum(1 for char in stripped if char.isprintable())
    return round(100 * printable / max(len(stripped), 1), 2)


def stable_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_pages(project_code: str, output_dir: Path, db_url: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    total_pages = 0

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, original_filename, stored_path
                FROM raw.source_files
                WHERE project_code = %s
                  AND file_ext = '.pdf'
                ORDER BY original_filename
                """,
                (project_code,),
            )
            source_files = cur.fetchall()

            for source_file in source_files:
                source_file_id = source_file["id"]
                pdf_path = Path(source_file["stored_path"])
                reader = PdfReader(str(pdf_path))

                cur.execute(
                    """
                    INSERT INTO raw.extraction_runs (
                        source_file_id, extractor_name, extractor_version, status, config
                    )
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        source_file_id,
                        "pypdf.extract_text",
                        "pypdf",
                        "running",
                        Jsonb({"output_dir": output_dir.as_posix()}),
                    ),
                )
                extraction_run_id = cur.fetchone()["id"]

                try:
                    for index, page in enumerate(reader.pages, start=1):
                        raw_text = page.extract_text() or ""
                        score = text_quality_score(raw_text)
                        page_hash = stable_hash(raw_text)
                        page_payload = {
                            "project_code": project_code,
                            "source_file_id": str(source_file_id),
                            "original_filename": source_file["original_filename"],
                            "page_no": index,
                            "raw_text": raw_text,
                            "raw_text_hash": page_hash,
                            "text_quality_score": score,
                        }
                        safe_stem = pdf_path.stem.replace(" ", "_").replace("/", "_").replace("\\", "_")
                        page_path = output_dir / f"{safe_stem}_page_{index:03d}.json"
                        page_path.write_text(
                            json.dumps(page_payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )

                        cur.execute(
                            """
                            INSERT INTO raw.pages (
                                source_file_id, extraction_run_id, page_no, raw_text,
                                raw_text_hash, text_quality_score
                            )
                            VALUES (%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (source_file_id, page_no) DO UPDATE
                            SET extraction_run_id = EXCLUDED.extraction_run_id,
                                raw_text = EXCLUDED.raw_text,
                                raw_text_hash = EXCLUDED.raw_text_hash,
                                text_quality_score = EXCLUDED.text_quality_score
                            """,
                            (source_file_id, extraction_run_id, index, raw_text, page_hash, score),
                        )
                        total_pages += 1

                    cur.execute(
                        """
                        UPDATE raw.extraction_runs
                        SET status = 'completed',
                            extraction_finished_at = now()
                        WHERE id = %s
                        """,
                        (extraction_run_id,),
                    )
                except Exception as exc:
                    cur.execute(
                        """
                        UPDATE raw.extraction_runs
                        SET status = 'failed',
                            extraction_finished_at = now(),
                            error_message = %s
                        WHERE id = %s
                        """,
                        (str(exc), extraction_run_id),
                    )
                    raise

        conn.commit()

    return total_pages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    total_pages = extract_pages(args.project, args.output, database_url(args.db, args.env))
    print(f"Extracted {total_pages} pages")


if __name__ == "__main__":
    main()
