from __future__ import annotations

import argparse
import json
import re
import subprocess
import string
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url
from cipp_contracts.extract.extract_office_text import (
    ExtractedPart,
    extract_docx,
    extract_xlsx,
    stable_hash,
    text_quality_score,
)


EXTRACTOR_NAME = "remaining_file_text"

TEXT_EXTS = {".txt", ".md", ".gdoc"}
XML_EXTS = {".xml"}
ODT_EXTS = {".odt"}
OOXML_EXTS = {".docx", ".xlsx"}
LEGACY_OFFICE_EXTS = {".doc", ".xls"}
NON_TEXT_EXTS = {".jpg", ".jpeg", ".png", ".dwg", ".zip", ""}

PRINTABLE = set(string.printable) | set("åäöÅÄÖ€–—•·§")


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    parts: list[ExtractedPart]
    reason: str | None = None


def canonical_ext(value: str | None) -> str:
    ext = (value or "").casefold().strip()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return ext


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_from_xml(path: Path) -> str:
    root = ElementTree.fromstring(path.read_bytes())
    values = [text.strip() for text in root.itertext() if text and text.strip()]
    return normalize_text("\n".join(values))


def text_from_odt(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        if "content.xml" not in archive.namelist():
            return ""
        root = ElementTree.fromstring(archive.read("content.xml"))
    values = [text.strip() for text in root.itertext() if text and text.strip()]
    return normalize_text("\n".join(values))


def text_from_plain_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return normalize_text(path.read_text(encoding=encoding))
        except UnicodeDecodeError:
            continue
    return normalize_text(path.read_bytes().decode("latin-1", errors="ignore"))


def printable_runs(text: str, min_length: int = 4) -> list[str]:
    runs: list[str] = []
    current: list[str] = []
    for char in text:
        if char in PRINTABLE and char not in "\x0b\x0c":
            current.append(char)
            continue
        if len(current) >= min_length:
            runs.append("".join(current))
        current = []
    if len(current) >= min_length:
        runs.append("".join(current))
    return runs


def text_from_legacy_binary(path: Path) -> str:
    data = path.read_bytes()
    candidates: list[str] = []
    candidates.extend(printable_runs(data.decode("latin-1", errors="ignore"), min_length=5))
    candidates.extend(printable_runs(data.decode("utf-16le", errors="ignore"), min_length=4))

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        value = normalize_text(value)
        if len(value) < 4:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)

    return normalize_text("\n".join(cleaned))


def find_soffice(explicit_path: Path | None = None) -> Path | None:
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    candidates.extend(
        [
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def convert_with_libreoffice(
    path: Path,
    ext: str,
    conversion_dir: Path,
    soffice_path: Path | None,
) -> Path | None:
    if soffice_path is None:
        return None
    conversion_dir.mkdir(parents=True, exist_ok=True)
    target_ext = ".docx" if ext == ".doc" else ".xlsx"
    convert_to = "docx" if ext == ".doc" else "xlsx"
    result = subprocess.run(
        [
            str(soffice_path),
            "--headless",
            "--convert-to",
            convert_to,
            "--outdir",
            str(conversion_dir),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    candidate = conversion_dir / f"{path.stem}{target_ext}"
    if result.returncode == 0 and candidate.exists():
        return candidate
    return None


def zip_listing(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        lines = []
        for info in archive.infolist():
            lines.append(f"{info.filename} | {info.file_size} bytes")
        return normalize_text("\n".join(lines))


def extract_file(
    path: Path,
    ext: str,
    conversion_dir: Path,
    soffice_path: Path | None,
) -> ExtractionResult:
    if not path.exists():
        return ExtractionResult("failed", [], "stored_path_missing")
    if ext == ".docx":
        return ExtractionResult("completed", extract_docx(path))
    if ext == ".xlsx":
        return ExtractionResult("completed", extract_xlsx(path))
    if ext in TEXT_EXTS:
        text = text_from_plain_file(path)
        return ExtractionResult("completed", [ExtractedPart(path.name, text)] if text else [])
    if ext in XML_EXTS:
        text = text_from_xml(path)
        return ExtractionResult("completed", [ExtractedPart(path.name, text)] if text else [])
    if ext in ODT_EXTS:
        text = text_from_odt(path)
        return ExtractionResult("completed", [ExtractedPart(path.name, text)] if text else [])
    if ext in LEGACY_OFFICE_EXTS:
        converted = convert_with_libreoffice(path, ext, conversion_dir, soffice_path)
        if converted and ext == ".doc":
            parts = extract_docx(converted)
            return ExtractionResult("completed", parts, "legacy_doc_converted_with_libreoffice")
        if converted and ext == ".xls":
            parts = extract_xlsx(converted)
            return ExtractionResult("completed", parts, "legacy_xls_converted_with_libreoffice")
        text = text_from_legacy_binary(path)
        if text:
            return ExtractionResult("completed", [ExtractedPart(path.name, text)], "legacy_binary_best_effort")
        return ExtractionResult("skipped", [], "legacy_binary_no_text_found")
    if ext == ".zip":
        try:
            listing = zip_listing(path)
        except zipfile.BadZipFile:
            part = ExtractedPart("metadata", f"ZIP archive listing failed: {path.name}")
            return ExtractionResult("skipped", [part], "zip_listing_failed")
        return ExtractionResult("completed", [ExtractedPart("zip_listing", listing)] if listing else [])
    if ext in {".jpg", ".jpeg", ".png"}:
        part = ExtractedPart(
            "metadata",
            f"Image file registered for OCR follow-up: {path.name}\n"
            "No visual OCR text was extracted in this run.",
        )
        return ExtractionResult("skipped", [part], "image_requires_ocr")
    if ext == ".dwg":
        part = ExtractedPart(
            "metadata",
            f"DWG drawing registered for CAD extraction follow-up: {path.name}\n"
            "No CAD geometry or drawing text was extracted in this run.",
        )
        return ExtractionResult("skipped", [part], "dwg_requires_cad_extractor")
    part = ExtractedPart(
        "metadata",
        f"Unsupported file registered for manual follow-up: {path.name}\n"
        f"Extension: {ext or '<none>'}",
    )
    return ExtractionResult("skipped", [part], f"unsupported_extension:{ext or '<none>'}")


def safe_output_name(source_file_id: str, original_filename: str) -> str:
    stem = Path(original_filename).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "file"
    return f"{stem}_{source_file_id[:8]}.json"


def resolve_stored_path(source_file: dict[str, Any]) -> Path:
    path = Path(source_file["stored_path"])
    if path.exists():
        return path

    stored_path = str(source_file["stored_path"])
    project_code = str(source_file["project_code"])
    aliases = {"pilot_001": "reference_001"}
    if project_code in aliases:
        candidate = Path(stored_path.replace(project_code, aliases[project_code], 1))
        if candidate.exists():
            return candidate

    return path


def process_source_file(
    conn: psycopg.Connection[Any],
    source_file: dict[str, Any],
    output_dir: Path,
    force: bool,
    soffice_path: Path | None,
) -> tuple[str, int]:
    source_file_id = source_file["id"]
    if not force:
        existing = conn.execute(
            "SELECT 1 FROM raw.pages WHERE source_file_id = %s LIMIT 1",
            (source_file_id,),
        ).fetchone()
        if existing:
            return "already_had_text", 0
    else:
        conn.execute("DELETE FROM raw.pages WHERE source_file_id = %s", (source_file_id,))

    ext = canonical_ext(source_file["file_ext"])
    path = resolve_stored_path(source_file)
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
            "python-stdlib-best-effort",
            "running",
            Jsonb({"output_dir": output_dir.as_posix(), "force": force}),
        ),
    ).fetchone()["id"]

    try:
        conversion_dir = output_dir / "_converted" / str(source_file["project_code"])
        result = extract_file(path, ext, conversion_dir, soffice_path)
        for page_no, part in enumerate(result.parts, start=1):
            text_hash = stable_hash(part.text)
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
                (
                    source_file_id,
                    run_id,
                    page_no,
                    part.text,
                    text_hash,
                    text_quality_score(part.text),
                ),
            )
        status = result.status
        db_status = "completed" if status == "skipped" else status
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status = %s,
                extraction_finished_at = now(),
                error_message = %s
            WHERE id = %s
            """,
            (db_status, result.reason, run_id),
        )
        write_record(output_dir, source_file, result)
        return status, len(result.parts)
    except Exception as exc:
        conn.execute(
            """
            UPDATE raw.extraction_runs
            SET status = 'failed',
                extraction_finished_at = now(),
                error_message = %s
            WHERE id = %s
            """,
            (str(exc), run_id),
        )
        write_record(output_dir, source_file, ExtractionResult("failed", [], str(exc)))
        return "failed", 0


def write_record(output_dir: Path, source_file: dict[str, Any], result: ExtractionResult) -> None:
    payload = {
        "source_file_id": str(source_file["id"]),
        "original_filename": source_file["original_filename"],
        "stored_path": source_file["stored_path"],
        "file_ext": source_file["file_ext"],
        "status": result.status,
        "reason": result.reason,
        "parts": [
            {
                "part_name": part.part_name,
                "raw_text": part.text,
                "raw_text_hash": stable_hash(part.text),
                "text_quality_score": text_quality_score(part.text),
            }
            for part in result.parts
        ],
    }
    output_path = output_dir / safe_output_name(str(source_file["id"]), source_file["original_filename"])
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_remaining(
    project_code: str | None,
    output_dir: Path,
    db_url: str,
    force: bool,
    soffice_path: Path | None,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {
        "files_seen": 0,
        "completed": 0,
        "skipped": 0,
        "failed": 0,
        "already_had_text": 0,
        "parts_extracted": 0,
    }
    target_exts = sorted(TEXT_EXTS | XML_EXTS | ODT_EXTS | OOXML_EXTS | LEGACY_OFFICE_EXTS | NON_TEXT_EXTS)

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        params: list[Any] = [target_exts]
        where = (
            "WHERE lower("
            "case "
            "when file_ext = '' then '' "
            "when file_ext like '.%%' then file_ext "
            "else '.' || file_ext "
            "end"
            ") = ANY(%s)"
        )
        if project_code:
            where += " AND project_code = %s"
            params.append(project_code)
        source_files = conn.execute(
            f"""
            SELECT id, project_code, original_filename, stored_path, file_ext
            FROM raw.source_files
            {where}
            ORDER BY project_code, original_filename, id
            """,
            params,
        ).fetchall()

        for source_file in source_files:
            counts["files_seen"] += 1
            project_dir = output_dir / source_file["project_code"]
            project_dir.mkdir(parents=True, exist_ok=True)
            status, parts = process_source_file(conn, source_file, project_dir, force, soffice_path)
            if status not in counts:
                counts[status] = 0
            counts[status] += 1
            counts["parts_extracted"] += parts
        conn.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--soffice-path", type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    counts = extract_remaining(
        project_code=args.project,
        output_dir=args.output,
        db_url=database_url(args.db, args.env),
        force=args.force,
        soffice_path=find_soffice(args.soffice_path),
    )
    print(
        "Remaining extraction: {completed} completed, {skipped} skipped, "
        "{failed} failed, {already_had_text} already had text, "
        "{parts_extracted} parts from {files_seen} files".format(**counts)
    )


if __name__ == "__main__":
    main()
