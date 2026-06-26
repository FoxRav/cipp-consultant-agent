from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pypdf import PdfReader

from cipp_contracts.config import database_url


IMPORTER = "project_operations_v1"

DOCUMENT_TYPE_LABELS = {
    "change_order_offer": ("Lisatyotarjous", "Urakan aikainen lisa- tai muutostyotarjous"),
    "contract_program": ("Urakkaohjelma", "Urakkaohjelma tai vastaava toteutusta ohjaava asiakirja"),
    "drawing": ("Piirustus", "Projektin piirustus tai kuva-aineisto"),
    "financial_final_report": ("Taloudellinen loppuselvitys", "Vastaanottoon tai lopputilitykseen liittyva rahaliikenneasiakirja"),
    "financial_tracking": ("Rahaliikenteen seuranta", "Projektin rahaliikenteen seuranta- tai taulukkoaineisto"),
    "handover_attachment": ("Vastaanoton liite", "Vastaanottoon liittyva liiteaineisto"),
    "handover_minutes": ("Vastaanottopoytakirja", "Vastaanotto- tai taloudellisen loppuselvityksen poytakirja"),
    "kickoff_meeting": ("Aloituskokous", "Tyomaan aloituskokouksen asiakirja"),
    "kvv_correction_photo": ("KVV-korjauskuva", "KVV-tarkastukseen tai korjaukseen liittyva kuva"),
    "kvv_inspection": ("KVV-tarkastus", "KVV- tai katselmusasiakirja"),
    "moisture_measurement_photo": ("Kosteusmittauskuva", "Kosteusmittaukseen liittyva kuva"),
    "payment_approval": ("Maksueran hyvaksynta", "Hyvaksytty maksueran tai laskun asiakirja"),
    "photo_documentation": ("Kuvadokumentaatio", "Projektin kuva-aineisto"),
    "project_correspondence": ("Projektikirjeenvaihto", "Projektin kirjeenvaihto tai tiedoksianto"),
    "project_management_table": ("Projektinhallintataulukko", "Projektinhallinnan taulukkoaineisto"),
    "resident_feedback": ("Asukaspalaute", "Asukkaan palaute tai reklamaatio"),
    "resident_notice": ("Asukastiedote", "Asukkaille tai kayttajille jaettu tiedote"),
    "site_diary": ("Tyomaapaivakirja", "Tyomaan paivakirja tai paivittainen seuranta"),
    "site_meeting": ("Tyomaakokous", "Tyomaakokouksen poytakirja tai liite"),
    "supervisor_comment_file": ("Valvojan kommenttitiedosto", "Valvojan kommentti- tai tarkastusaineisto"),
    "technical_work_description": ("Tekninen tyoselostus", "Tekninen tyoselostus tai menetelmakuvaus"),
    "video_inspection_report": ("Videotarkastusraportti", "Valvojan videotarkastusraportti tai kommenttiaineisto"),
    "work_plan": ("Tyosuunnitelma", "Urakoitsijan tyosuunnitelma"),
}

SUPPORTED_EXTS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".dwg",
    ".zip",
    ".gdoc",
    "",
}


@dataclass(frozen=True)
class FileClassification:
    document_type: str
    event_type: str | None = None
    observation_type: str | None = None
    creates_handover: bool = False
    creates_payment: bool = False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_pdf(path: Path) -> tuple[int | None, bool | None, bool | None]:
    if path.suffix.lower() != ".pdf":
        return None, None, None
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        sample_text = "\n".join(
            (page.extract_text() or "") for page in reader.pages[: min(3, page_count)]
        )
        has_text_layer = bool(sample_text.strip())
        return page_count, has_text_layer, not has_text_layer
    except Exception:
        return None, None, None


def normalize_text(value: str) -> str:
    return value.casefold().replace("_", " ").replace("-", " ")


def classify(path: Path) -> FileClassification:
    text = normalize_text(" ".join(path.parts))
    ext = path.suffix.lower()

    if "kvv ja vastaanotto" in text:
        return FileClassification("handover_minutes", "handover", "handover", True)
    if "aloituskokous" in text:
        return FileClassification("kickoff_meeting", "kickoff_meeting")
    if re.search(r"\btmk\b|työmaakokous|tyomaakokous", text):
        return FileClassification("site_meeting", "site_meeting")
    if "videontarkast" in text or "videotarkast" in text:
        return FileClassification("video_inspection_report", "video_inspection", "quality")
    if "vastaanotto" in text or "taloudellinen loppuselvitys" in text:
        return FileClassification("handover_minutes", "handover", "handover", True)
    if "maksuer" in text or "maksuposti" in text or "hyväksytyt laskut" in text or "hyvaks" in text:
        return FileClassification("payment_approval", "payment_approval", creates_payment=True)
    if "rahaliikenne" in text or "hyvityslasku" in text:
        return FileClassification("financial_tracking", "financial_event")
    if "lisäty" in text or "lisaty" in text or "change order" in text:
        return FileClassification("change_order_offer", "change_order")
    if "työmaapäivä" in text or "tyomaapaiva" in text:
        return FileClassification("site_diary", "site_diary")
    if "tiedotteet" in text or "tiedote" in text:
        return FileClassification("resident_notice", "resident_notice")
    if "valvojan" in text or "katselmus" in text or "kvv" in text:
        return FileClassification("kvv_inspection", "inspection", "supervisor_note")
    if "projektihallinta" in text:
        return FileClassification("project_management_table", "project_management")
    if "työsuojelu" in text or "tyosuojelu" in text or "työsuunnitelma" in text:
        return FileClassification("safety_plan", "work_plan")
    if "urakkasopimus" in text:
        return FileClassification("main_contract")
    if "tarjouspyynt" in text:
        return FileClassification("rfq")
    if "urakkaneuvottelu" in text:
        return FileClassification("negotiation_minutes", "negotiation")
    if "tarjoukset" in text or "tarjous" in text:
        return FileClassification("contractor_offer")
    if "piirustus" in text or ext == ".dwg":
        return FileClassification("drawing")
    if "aikataulu" in text:
        return FileClassification("project_schedule", "schedule")
    if "työselostus" in text or "tyoselostus" in text:
        return FileClassification("technical_work_description")
    if ext in {".jpg", ".jpeg", ".png"}:
        return FileClassification("photo_documentation", "photo_documentation")
    return FileClassification("project_note")


def parse_date(path: Path) -> date | None:
    text = " ".join(path.parts)
    match = re.search(r"(?<!\d)(\d{1,2})[._-](\d{1,2})[._-](20\d{2})(?!\d)", text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def ensure_document_types(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        for code, (label, description) in DOCUMENT_TYPE_LABELS.items():
            cur.execute(
                """
                INSERT INTO ref.document_types (code, label, description)
                VALUES (%s,%s,%s)
                ON CONFLICT (code) DO UPDATE
                SET label = EXCLUDED.label,
                    description = EXCLUDED.description
                """,
                (code, label, description),
            )


def ensure_project(conn: psycopg.Connection[Any], project_code: str) -> None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT project_code FROM core.projects WHERE project_code = %s",
            (project_code,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown project_code in core.projects: {project_code}")


def clear_previous_import(conn: psycopg.Connection[Any], project_code: str) -> None:
    with conn.cursor() as cur:
        for table in (
            "ops.project_observations",
            "ops.handover_records",
            "ops.payment_approvals",
            "ops.project_events",
        ):
            cur.execute(
                f"DELETE FROM {table} WHERE project_code = %s AND metadata->>'importer' = %s",
                (project_code, IMPORTER),
            )


def upsert_source_file(
    conn: psycopg.Connection[Any],
    project_code: str,
    path: Path,
    root: Path,
    classification: FileClassification,
) -> str:
    page_count, has_text_layer, needs_ocr = inspect_pdf(path)
    file_hash = sha256_file(path)
    relative_path = path.relative_to(root.parent).as_posix()
    notes = f"Imported recursively from operation package: {relative_path}"
    with conn.cursor() as cur:
        source_file_id = cur.execute(
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
                project_code,
                path.name,
                path.as_posix(),
                classification.document_type,
                path.suffix.lower(),
                file_hash,
                page_count,
                path.stat().st_size,
                has_text_layer,
                needs_ocr,
                notes,
            ),
        ).fetchone()[0]
        cur.execute(
            "DELETE FROM raw.source_file_document_types WHERE source_file_id = %s",
            (source_file_id,),
        )
        cur.execute(
            """
            INSERT INTO raw.source_file_document_types (
                source_file_id, document_type, is_primary, notes
            )
            VALUES (%s,%s,true,%s)
            """,
            (source_file_id, classification.document_type, notes),
        )
    return str(source_file_id)


def insert_event(
    conn: psycopg.Connection[Any],
    project_code: str,
    source_file_id: str,
    path: Path,
    root: Path,
    classification: FileClassification,
) -> str | None:
    if classification.event_type is None:
        return None
    event_date = parse_date(path)
    relative_path = path.relative_to(root.parent).as_posix()
    title = path.stem or path.name
    with conn.cursor() as cur:
        event_id = cur.execute(
            """
            INSERT INTO ops.project_events (
                project_code, event_type, event_date, title, source_file_id,
                source_document_type, summary, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                project_code,
                classification.event_type,
                event_date,
                title,
                source_file_id,
                classification.document_type,
                f"Imported operational file: {relative_path}",
                Jsonb({"importer": IMPORTER, "relative_path": relative_path}),
            ),
        ).fetchone()[0]
    return str(event_id)


def insert_observation(
    conn: psycopg.Connection[Any],
    project_code: str,
    event_id: str | None,
    source_file_id: str,
    path: Path,
    root: Path,
    classification: FileClassification,
) -> None:
    if classification.observation_type is None:
        return
    relative_path = path.relative_to(root.parent).as_posix()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.project_observations (
                project_event_id, project_code, observation_type, issue_text,
                source_file_id, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                event_id,
                project_code,
                classification.observation_type,
                f"Operational source requires detailed review: {path.stem or path.name}",
                source_file_id,
                Jsonb({"importer": IMPORTER, "relative_path": relative_path}),
            ),
        )


def insert_handover(
    conn: psycopg.Connection[Any],
    project_code: str,
    source_file_id: str,
    path: Path,
    root: Path,
) -> None:
    relative_path = path.relative_to(root.parent).as_posix()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.handover_records (
                project_code, handover_date, source_file_id, accepted_with_remarks,
                handover_summary, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                project_code,
                parse_date(path),
                source_file_id,
                True,
                f"Handover-related operational source imported: {path.stem or path.name}",
                Jsonb({"importer": IMPORTER, "relative_path": relative_path}),
            ),
        )


def insert_payment(
    conn: psycopg.Connection[Any],
    project_code: str,
    source_file_id: str,
    path: Path,
    root: Path,
) -> None:
    relative_path = path.relative_to(root.parent).as_posix()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.payment_approvals (
                project_code, source_file_id, approval_date, invoice_or_payment_ref,
                payment_item_text, approval_status, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                project_code,
                source_file_id,
                parse_date(path),
                path.stem or path.name,
                f"Payment-related operational source imported: {path.stem or path.name}",
                "imported_for_review",
                Jsonb({"importer": IMPORTER, "relative_path": relative_path}),
            ),
        )


def import_operations(project_code: str, source_dir: Path, report: Path, db_url: str) -> dict[str, int]:
    source_dir = source_dir.resolve()
    files = sorted(
        [
            path
            for path in source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS
        ],
        key=lambda path: path.as_posix().casefold(),
    )
    counts = {
        "files": 0,
        "events": 0,
        "observations": 0,
        "handovers": 0,
        "payments": 0,
    }
    by_document_type: dict[str, int] = {}

    with psycopg.connect(db_url) as conn:
        ensure_project(conn, project_code)
        ensure_document_types(conn)
        clear_previous_import(conn, project_code)

        for path in files:
            classification = classify(path.relative_to(source_dir.parent))
            source_file_id = upsert_source_file(conn, project_code, path, source_dir, classification)
            event_id = insert_event(conn, project_code, source_file_id, path, source_dir, classification)
            insert_observation(conn, project_code, event_id, source_file_id, path, source_dir, classification)
            if classification.creates_handover:
                insert_handover(conn, project_code, source_file_id, path, source_dir)
            if classification.creates_payment:
                insert_payment(conn, project_code, source_file_id, path, source_dir)

            counts["files"] += 1
            counts["events"] += 1 if event_id else 0
            counts["observations"] += 1 if classification.observation_type else 0
            counts["handovers"] += 1 if classification.creates_handover else 0
            counts["payments"] += 1 if classification.creates_payment else 0
            by_document_type[classification.document_type] = (
                by_document_type.get(classification.document_type, 0) + 1
            )
        conn.commit()

    write_report(report, project_code, source_dir, counts, by_document_type)
    return counts


def write_report(
    report: Path,
    project_code: str,
    source_dir: Path,
    counts: dict[str, int],
    by_document_type: dict[str, int],
) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Project Operations Import",
        "",
        f"- Project: `{project_code}`",
        f"- Source: `{source_dir.as_posix()}`",
        f"- Files: {counts['files']}",
        f"- Events: {counts['events']}",
        f"- Observations: {counts['observations']}",
        f"- Handovers: {counts['handovers']}",
        f"- Payment approvals: {counts['payments']}",
        "",
        "## Document Types",
        "",
    ]
    for document_type, count in sorted(by_document_type.items()):
        lines.append(f"- `{document_type}`: {count}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    counts = import_operations(
        project_code=args.project,
        source_dir=args.input,
        report=args.report,
        db_url=database_url(args.db, args.env),
    )
    print(
        "Imported {files} files, {events} events, {observations} observations, "
        "{handovers} handovers, {payments} payments".format(**counts)
    )


if __name__ == "__main__":
    main()
