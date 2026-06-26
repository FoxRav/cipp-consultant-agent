from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pypdf import PdfReader

from cipp_contracts.config import database_url
from cipp_contracts.extract.extract_office_text import stable_hash, text_quality_score


EXTRACTOR_NAME = "autodesk_dwg_trueview"
DERIVED_DOCUMENT_TYPE = "drawing_index"


def find_accoreconsole(explicit_path: Path | None = None) -> Path | None:
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    found = shutil.which("accoreconsole")
    if found:
        candidates.append(Path(found))
    candidates.extend(
        [
            Path(r"C:\Program Files\Autodesk\DWG TrueView 2027 - English\accoreconsole.exe"),
            Path(r"C:\Program Files\Autodesk\DWG TrueView 2027\accoreconsole.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_stored_path(source_file: dict[str, Any]) -> Path:
    path = Path(source_file["stored_path"])
    if path.exists():
        return path
    aliases = {"pilot_001": "reference_001"}
    project_code = str(source_file["project_code"])
    if project_code in aliases:
        candidate = Path(str(source_file["stored_path"]).replace(project_code, aliases[project_code], 1))
        if candidate.exists():
            return candidate
    return path


def write_trueview_script(script_path: Path, output_pdf: Path) -> None:
    # The command sequence is intentionally conservative. Some DWG files/layouts
    # still require manual plot setup; the run log preserves TrueView output.
    lines = [
        "PLOT",
        "Y",
        "Model",
        "DWG To PDF.pc3",
        "ISO full bleed A3 (420.00 x 297.00 MM)",
        "Millimeters",
        "Landscape",
        "N",
        "Extents",
        "Fit",
        "Center",
        "Y",
        "monochrome.ctb",
        "Y",
        "A",
        str(output_pdf),
        "N",
        "Y",
        "QUIT",
        "Y",
    ]
    script_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def run_trueview(
    accoreconsole: Path,
    dwg_path: Path,
    script_path: Path,
    timeout: int,
) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        [str(accoreconsole), "/i", str(dwg_path), "/s", str(script_path), "/l", "en-US"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def clean_process_text(value: str) -> str:
    # Accoreconsole commonly writes UTF-16-ish text through redirected streams.
    return value.replace("\x00", "")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_pdf(path: Path) -> tuple[int | None, bool | None, bool | None]:
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        sample_text = "\n".join((page.extract_text() or "") for page in reader.pages[: min(3, page_count)])
        has_text_layer = bool(sample_text.strip())
        return page_count, has_text_layer, not has_text_layer
    except Exception:
        return None, None, None


def write_log(
    output_dir: Path,
    source_file: dict[str, Any],
    output_pdf: Path,
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
    payload = {
        "source_file_id": str(source_file["id"]),
        "project_code": source_file["project_code"],
        "original_filename": source_file["original_filename"],
        "output_pdf": output_pdf.as_posix(),
        "returncode": returncode,
        "stdout": clean_process_text(stdout),
        "stderr": clean_process_text(stderr),
    }
    log_path = output_dir / f"{Path(source_file['original_filename']).stem}_trueview_run.json"
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register_derived_pdf(
    conn: psycopg.Connection[Any],
    source_file: dict[str, Any],
    output_pdf: Path,
) -> Any:
    page_count, has_text_layer, needs_ocr = inspect_pdf(output_pdf)
    file_hash = sha256_file(output_pdf)
    notes = f"Derived PDF converted from DWG source file {source_file['original_filename']} with Autodesk DWG TrueView."
    derived_id = conn.execute(
        """
        INSERT INTO raw.source_files (
            project_code, original_filename, stored_path, document_type, file_ext,
            sha256, page_count, byte_size, has_text_layer, needs_ocr, notes
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (sha256) DO UPDATE
        SET project_code = EXCLUDED.project_code,
            original_filename = EXCLUDED.original_filename,
            stored_path = EXCLUDED.stored_path,
            document_type = EXCLUDED.document_type,
            file_ext = EXCLUDED.file_ext,
            page_count = EXCLUDED.page_count,
            byte_size = EXCLUDED.byte_size,
            has_text_layer = EXCLUDED.has_text_layer,
            needs_ocr = EXCLUDED.needs_ocr,
            notes = EXCLUDED.notes
        RETURNING id
        """,
        (
            source_file["project_code"],
            output_pdf.name,
            output_pdf.as_posix(),
            DERIVED_DOCUMENT_TYPE,
            ".pdf",
            file_hash,
            page_count,
            output_pdf.stat().st_size,
            has_text_layer,
            needs_ocr,
            notes,
        ),
    ).fetchone()["id"]
    conn.execute(
        """
        INSERT INTO raw.source_file_document_types (
            source_file_id, document_type, is_primary, notes
        )
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (source_file_id, document_type) DO UPDATE
        SET is_primary = EXCLUDED.is_primary,
            notes = EXCLUDED.notes
        """,
        (derived_id, DERIVED_DOCUMENT_TYPE, True, notes),
    )
    return derived_id


def process_dwg(
    conn: psycopg.Connection[Any],
    source_file: dict[str, Any],
    output_base: Path,
    accoreconsole: Path,
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

    project_dir = output_base / str(source_file["project_code"])
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    dwg_path = resolve_stored_path(source_file)
    output_pdf = project_dir / f"{dwg_path.stem}.pdf"
    script_path = project_dir / f"{dwg_path.stem}_plot.scr"
    write_trueview_script(script_path, output_pdf)

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
            "dwg-trueview-2027-accoreconsole",
            "running",
            Jsonb(
                {
                    "output_dir": project_dir.as_posix(),
                    "accoreconsole": accoreconsole.as_posix(),
                    "script": script_path.as_posix(),
                    "output_pdf": output_pdf.as_posix(),
                }
            ),
        ),
    ).fetchone()["id"]

    if not dwg_path.exists():
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status='failed',
                extraction_finished_at=now(),
                error_message='stored_path_missing'
            WHERE id=%s
            """,
            (run_id,),
        )
        return "failed", 0

    try:
        returncode, stdout, stderr = run_trueview(
            accoreconsole.resolve(),
            dwg_path.resolve(),
            script_path.resolve(),
            timeout,
        )
        stdout = clean_process_text(stdout)
        stderr = clean_process_text(stderr)
        write_log(project_dir, source_file, output_pdf, returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status='failed',
                extraction_finished_at=now(),
                error_message='trueview_timeout'
            WHERE id=%s
            """,
            (run_id,),
        )
        return "failed", 0

    if output_pdf.exists():
        derived_pdf_id = register_derived_pdf(conn, source_file, output_pdf)
        text = (
            f"DWG converted to PDF with Autodesk DWG TrueView.\n"
            f"Source: {dwg_path.name}\nOutput PDF: {output_pdf.as_posix()}"
            f"\nDerived PDF source_file_id: {derived_pdf_id}"
        )
        conn.execute("DELETE FROM raw.pages WHERE source_file_id = %s", (source_file_id,))
        conn.execute(
            """
            INSERT INTO raw.pages (
                source_file_id, extraction_run_id, page_no, raw_text,
                raw_text_hash, text_quality_score
            )
            VALUES (%s,%s,1,%s,%s,%s)
            ON CONFLICT (source_file_id, page_no) DO UPDATE
            SET extraction_run_id = EXCLUDED.extraction_run_id,
                raw_text = EXCLUDED.raw_text,
                raw_text_hash = EXCLUDED.raw_text_hash,
                text_quality_score = EXCLUDED.text_quality_score
            """,
            (source_file_id, run_id, text, stable_hash(text), text_quality_score(text)),
        )
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status='completed',
                extraction_finished_at=now()
            WHERE id=%s
            """,
            (run_id,),
        )
        return "completed", 1

    message = (stderr or stdout or f"trueview_returncode_{returncode}")[:1000]
    conn.execute(
        """
        UPDATE raw.extraction_runs
        SET status='failed',
            extraction_finished_at=now(),
            error_message=%s
        WHERE id=%s
        """,
        (message, run_id),
    )
    return "failed", 0


def extract_dwg(
    project_code: str | None,
    output_dir: Path,
    db_url: str,
    accoreconsole: Path,
    timeout: int,
    force: bool,
) -> dict[str, int]:
    counts = {"files_seen": 0, "completed": 0, "failed": 0, "already_completed": 0, "parts": 0}
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        params: list[Any] = []
        where = "WHERE lower(file_ext) = '.dwg'"
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
            status, parts = process_dwg(
                conn,
                source_file,
                output_dir,
                accoreconsole,
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
    parser.add_argument("--accoreconsole-path", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    accoreconsole = find_accoreconsole(args.accoreconsole_path)
    if accoreconsole is None:
        raise FileNotFoundError("Autodesk accoreconsole.exe not found")

    counts = extract_dwg(
        project_code=args.project,
        output_dir=args.output,
        db_url=database_url(args.db, args.env),
        accoreconsole=accoreconsole,
        timeout=args.timeout,
        force=args.force,
    )
    print(
        "DWG TrueView: {completed} completed, {failed} failed, "
        "{already_completed} already done, {parts} parts from {files_seen} files".format(**counts)
    )


if __name__ == "__main__":
    main()
