from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url


EXTRACTOR_NAME = "office_ooxml_text"
SUPPORTED_EXTS = {".docx", ".xlsx"}
LEGACY_EXTS = {".doc", ".xls"}

XML_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}


@dataclass(frozen=True)
class ExtractedPart:
    part_name: str
    text: str


def stable_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def text_quality_score(text: str | None) -> float:
    if not text:
        return 0.0
    stripped = text.strip()
    if not stripped:
        return 0.0
    printable = sum(1 for char in stripped if char.isprintable())
    return round(100 * printable / max(len(stripped), 1), 2)


def normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def xml_text_nodes(root: ElementTree.Element) -> list[str]:
    values: list[str] = []
    for elem in root.iter():
        if elem.text and elem.tag.endswith("}t"):
            values.append(elem.text)
        elif elem.text and elem.tag.endswith("}instrText"):
            values.append(elem.text)
    return values


def extract_docx(path: Path) -> list[ExtractedPart]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        parts: list[ExtractedPart] = []
        for name in (
            "word/document.xml",
            "word/header1.xml",
            "word/header2.xml",
            "word/footer1.xml",
            "word/footer2.xml",
        ):
            if name not in names:
                continue
            root = ElementTree.fromstring(archive.read(name))
            text = normalize_text("\n".join(xml_text_nodes(root)))
            if text:
                parts.append(ExtractedPart(name, text))
        return parts


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("x:si", XML_NS):
        strings.append(normalize_text(" ".join(xml_text_nodes(item))))
    return strings


def read_sheet_names(archive: zipfile.ZipFile) -> dict[str, str]:
    if "xl/workbook.xml" not in archive.namelist():
        return {}
    root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    result: dict[str, str] = {}
    for index, sheet in enumerate(root.findall(".//x:sheet", XML_NS), start=1):
        result[f"xl/worksheets/sheet{index}.xml"] = sheet.attrib.get("name", f"Sheet{index}")
    return result


def cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.find("x:v", XML_NS)
    inline = cell.find("x:is", XML_NS)
    if inline is not None:
        return normalize_text(" ".join(xml_text_nodes(inline)))
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (IndexError, ValueError):
            return raw
    return raw


def extract_xlsx(path: Path) -> list[ExtractedPart]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive)
        sheet_names = read_sheet_names(archive)
        parts: list[ExtractedPart] = []
        sheet_files = sorted(
            name
            for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        for sheet_file in sheet_files:
            root = ElementTree.fromstring(archive.read(sheet_file))
            lines: list[str] = []
            for row in root.findall(".//x:row", XML_NS):
                values = [cell_value(cell, shared_strings) for cell in row.findall("x:c", XML_NS)]
                values = [value for value in values if value]
                if values:
                    lines.append(" | ".join(values))
            text = normalize_text("\n".join(lines))
            if text:
                label = sheet_names.get(sheet_file, Path(sheet_file).stem)
                parts.append(ExtractedPart(label, text))
        return parts


def extract_parts(path: Path) -> list[ExtractedPart]:
    ext = path.suffix.lower()
    if ext == ".docx":
        return extract_docx(path)
    if ext == ".xlsx":
        return extract_xlsx(path)
    if ext in LEGACY_EXTS:
        return []
    raise ValueError(f"Unsupported Office extension: {ext}")


def safe_output_name(source_file_id: str, original_filename: str) -> str:
    stem = Path(original_filename).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "office"
    return f"{stem}_{source_file_id[:8]}.json"


def extract_office_text(project_code: str, output_dir: Path, db_url: str) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {
        "files_seen": 0,
        "files_extracted": 0,
        "parts_extracted": 0,
        "legacy_skipped": 0,
        "failed": 0,
    }

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        source_files = conn.execute(
            """
            SELECT id, original_filename, stored_path, file_ext
            FROM raw.source_files
            WHERE project_code = %s
              AND file_ext IN ('.docx', '.xlsx', '.doc', '.xls')
            ORDER BY original_filename, id
            """,
            (project_code,),
        ).fetchall()

        for source_file in source_files:
            counts["files_seen"] += 1
            source_file_id = source_file["id"]
            source_path = Path(source_file["stored_path"])
            ext = source_file["file_ext"]

            if ext in LEGACY_EXTS:
                counts["legacy_skipped"] += 1
                write_skip_record(output_dir, source_file, "legacy_binary_office_requires_conversion")
                continue

            extraction_run_id = conn.execute(
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
                    "stdlib-zip-xml",
                    "running",
                    Jsonb({"output_dir": output_dir.as_posix()}),
                ),
            ).fetchone()["id"]

            try:
                parts = extract_parts(source_path)
                payload_parts = []
                for page_no, part in enumerate(parts, start=1):
                    text_hash = stable_hash(part.text)
                    score = text_quality_score(part.text)
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
                        (source_file_id, extraction_run_id, page_no, part.text, text_hash, score),
                    )
                    payload_parts.append(
                        {
                            "part_name": part.part_name,
                            "page_no": page_no,
                            "raw_text": part.text,
                            "raw_text_hash": text_hash,
                            "text_quality_score": score,
                        }
                    )

                conn.execute(
                    """
                    UPDATE raw.extraction_runs
                    SET status = 'completed',
                        extraction_finished_at = now()
                    WHERE id = %s
                    """,
                    (extraction_run_id,),
                )
                write_extract_record(output_dir, source_file, payload_parts)
                counts["files_extracted"] += 1 if parts else 0
                counts["parts_extracted"] += len(parts)
            except Exception as exc:
                counts["failed"] += 1
                conn.execute(
                    """
                    UPDATE raw.extraction_runs
                    SET status = 'failed',
                        extraction_finished_at = now(),
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(exc), extraction_run_id),
                )
                write_skip_record(output_dir, source_file, f"failed: {exc}")

        conn.commit()

    return counts


def write_extract_record(
    output_dir: Path,
    source_file: dict[str, Any],
    parts: list[dict[str, Any]],
) -> None:
    payload = {
        "source_file_id": str(source_file["id"]),
        "original_filename": source_file["original_filename"],
        "stored_path": source_file["stored_path"],
        "status": "completed",
        "parts": parts,
    }
    output_path = output_dir / safe_output_name(str(source_file["id"]), source_file["original_filename"])
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_skip_record(output_dir: Path, source_file: dict[str, Any], reason: str) -> None:
    payload = {
        "source_file_id": str(source_file["id"]),
        "original_filename": source_file["original_filename"],
        "stored_path": source_file["stored_path"],
        "status": "skipped",
        "reason": reason,
    }
    output_path = output_dir / safe_output_name(str(source_file["id"]), source_file["original_filename"])
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    counts = extract_office_text(args.project, args.output, database_url(args.db, args.env))
    print(
        "Office extraction: {files_extracted}/{files_seen} files, "
        "{parts_extracted} parts, {legacy_skipped} legacy skipped, {failed} failed".format(
            **counts
        )
    )


if __name__ == "__main__":
    main()
