from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url
from cipp_contracts.extract.extract_office_text import stable_hash, text_quality_score


EXTRACTOR_NAME = "doclayout_ai_visual_ocr"
DEFAULT_VISUAL_EXTS = {".jpg", ".jpeg", ".png"}


def canonical_ext(value: str | None) -> str:
    ext = (value or "").casefold().strip()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return ext


def find_kuvien_parsinta(explicit_path: Path | None = None) -> str | None:
    if explicit_path and explicit_path.exists():
        return str(explicit_path)
    candidates = [
        Path(r"F:\-DEV-\95.Kuvien-parsinta-SOTA\.venv\Scripts\kuvien-parsinta.exe"),
        Path(r"C:\Python3_10_11\Scripts\kuvien-parsinta.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("kuvien-parsinta")
    if found:
        return found
    return None


def resolve_stored_path(source_file: dict[str, Any]) -> Path:
    path = Path(source_file["stored_path"])
    if path.exists():
        return path
    stored_path = str(source_file["stored_path"])
    aliases = {"pilot_001": "reference_001"}
    project_code = str(source_file["project_code"])
    if project_code in aliases:
        candidate = Path(stored_path.replace(project_code, aliases[project_code], 1))
        if candidate.exists():
            return candidate
    return path


def run_visual_ocr(
    input_path: Path,
    output_dir: Path,
    cli_path: str,
    engine: str,
    quality: str,
    no_pdf: bool,
    timeout: int,
) -> tuple[int, str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        cli_path,
        "parse",
        str(input_path),
        "--out-dir",
        str(output_dir),
        "--engine",
        engine,
        "--quality",
        quality,
    ]
    if no_pdf:
        command.append("--no-pdf")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def read_markdown(output_dir: Path, source_path: Path) -> str:
    direct = output_dir / f"{source_path.stem}.md"
    if direct.exists():
        return direct.read_text(encoding="utf-8-sig", errors="replace")
    markdowns = sorted(output_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)
    if markdowns:
        return markdowns[0].read_text(encoding="utf-8-sig", errors="replace")
    return ""


def write_run_log(
    output_dir: Path,
    source_file: dict[str, Any],
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
    payload = {
        "source_file_id": str(source_file["id"]),
        "project_code": source_file["project_code"],
        "original_filename": source_file["original_filename"],
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    log_path = output_dir / f"{Path(source_file['original_filename']).stem}_ocr_run.json"
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_visual_file(
    conn: psycopg.Connection[Any],
    source_file: dict[str, Any],
    base_output_dir: Path,
    cli_path: str,
    engine: str,
    quality: str,
    no_pdf: bool,
    timeout: int,
    force: bool,
) -> tuple[str, int]:
    source_file_id = source_file["id"]
    if not force:
        existing = conn.execute(
            """
            SELECT 1
            FROM raw.extraction_runs
            WHERE source_file_id = %s
              AND extractor_name = %s
              AND status = 'completed'
            LIMIT 1
            """,
            (source_file_id, EXTRACTOR_NAME),
        ).fetchone()
        if existing:
            return "already_completed", 0

    input_path = resolve_stored_path(source_file)
    output_dir = base_output_dir / str(source_file["project_code"])
    run_id = conn.execute(
        """
        INSERT INTO raw.extraction_runs (
            source_file_id, extractor_name, extractor_version, status, config
        )
        VALUES (%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            source_file_id,
            EXTRACTOR_NAME,
            "doclayout-ai-cli",
            "running",
            Jsonb(
                {
                    "output_dir": output_dir.as_posix(),
                    "engine": engine,
                    "quality": quality,
                    "no_pdf": no_pdf,
                    "cli_path": cli_path,
                }
            ),
        ),
    ).fetchone()["id"]

    if not input_path.exists():
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status = 'failed',
                extraction_finished_at = now(),
                error_message = 'stored_path_missing'
            WHERE id = %s
            """,
            (run_id,),
        )
        return "failed", 0

    try:
        returncode, stdout, stderr = run_visual_ocr(
            input_path,
            output_dir,
            cli_path,
            engine,
            quality,
            no_pdf,
            timeout,
        )
        write_run_log(output_dir, source_file, returncode, stdout, stderr)
        if returncode != 0:
            conn.execute(
                """
                UPDATE raw.extraction_runs
                SET status = 'failed',
                    extraction_finished_at = now(),
                    error_message = %s
                WHERE id = %s
                """,
                ((stderr or stdout or "visual_ocr_failed")[:1000], run_id),
            )
            return "failed", 0

        text = read_markdown(output_dir, input_path)
        if not text.strip():
            conn.execute(
                """
                UPDATE raw.extraction_runs
                SET status = 'completed',
                    extraction_finished_at = now(),
                    error_message = 'no_markdown_text_found'
                WHERE id = %s
                """,
                (run_id,),
            )
            return "completed_no_text", 0

        conn.execute("DELETE FROM raw.pages WHERE source_file_id = %s", (source_file_id,))
        conn.execute(
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
            (source_file_id, run_id, 1, text, stable_hash(text), text_quality_score(text)),
        )
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status = 'completed',
                extraction_finished_at = now()
            WHERE id = %s
            """,
            (run_id,),
        )
        return "completed", 1
    except subprocess.TimeoutExpired:
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status = 'failed',
                extraction_finished_at = now(),
                error_message = 'visual_ocr_timeout'
            WHERE id = %s
            """,
            (run_id,),
        )
        return "failed", 0


def extract_visual_ocr(
    project_code: str | None,
    output_dir: Path,
    db_url: str,
    cli_path: str,
    engine: str,
    quality: str,
    no_pdf: bool,
    timeout: int,
    force: bool,
) -> dict[str, int]:
    counts = {
        "files_seen": 0,
        "completed": 0,
        "completed_no_text": 0,
        "failed": 0,
        "already_completed": 0,
        "parts": 0,
    }
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        params: list[Any] = [sorted(DEFAULT_VISUAL_EXTS)]
        where = "WHERE lower(case when file_ext like '.%%' then file_ext else '.' || file_ext end) = ANY(%s)"
        if project_code:
            where += " AND project_code = %s"
            params.append(project_code)
        rows = conn.execute(
            f"""
            SELECT id, project_code, original_filename, stored_path, file_ext
            FROM raw.source_files
            {where}
            ORDER BY project_code, original_filename, id
            """,
            params,
        ).fetchall()
        for source_file in rows:
            counts["files_seen"] += 1
            status, parts = process_visual_file(
                conn,
                source_file,
                output_dir,
                cli_path,
                engine,
                quality,
                no_pdf,
                timeout,
                force,
            )
            counts[status] += 1
            counts["parts"] += parts
        conn.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kuvien-parsinta-path", type=Path)
    parser.add_argument("--engine", default="hybrid")
    parser.add_argument("--quality", default="max")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--write-pdf", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    cli_path = find_kuvien_parsinta(args.kuvien_parsinta_path)
    if cli_path is None:
        raise FileNotFoundError("kuvien-parsinta CLI not found")

    counts = extract_visual_ocr(
        project_code=args.project,
        output_dir=args.output,
        db_url=database_url(args.db, args.env),
        cli_path=cli_path,
        engine=args.engine,
        quality=args.quality,
        no_pdf=not args.write_pdf,
        timeout=args.timeout,
        force=args.force,
    )
    print(
        "Visual OCR: {completed} completed, {completed_no_text} without text, "
        "{failed} failed, {already_completed} already done, {parts} parts "
        "from {files_seen} files".format(**counts)
    )


if __name__ == "__main__":
    main()
