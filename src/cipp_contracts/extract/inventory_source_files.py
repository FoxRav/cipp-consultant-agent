from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pypdf import PdfReader

from cipp_contracts.config import database_url


@dataclass(frozen=True)
class DocumentTypeGuess:
    primary: str
    all_types: tuple[str, ...]
    notes: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guess_document_type(filename: str) -> DocumentTypeGuess:
    normalized = filename.casefold()
    if "yse1998" in normalized or "yse 1998" in normalized:
        return DocumentTypeGuess("yse_1998", ("yse_1998",))
    if "liiteluettelo" in normalized:
        return DocumentTypeGuess("attachment_index", ("attachment_index",))
    if "urakkaneuvottelupöytäkirjan liite" in normalized:
        return DocumentTypeGuess("negotiation_attachment", ("negotiation_attachment",))
    if "yksikköhint" in normalized:
        return DocumentTypeGuess("unit_prices", ("unit_prices",))
    if "maksuerä" in normalized:
        return DocumentTypeGuess("payment_schedule", ("payment_schedule",))
    if "piirustus" in normalized:
        return DocumentTypeGuess("drawing_index", ("drawing_index",))
    if "tarjouspyyntöliite" in normalized:
        return DocumentTypeGuess("rfq_clarification", ("rfq_clarification",))
    if "tarjouspyynnön tarkennus" in normalized or "tarkennus" in normalized:
        return DocumentTypeGuess("rfq_clarification", ("rfq_clarification",))
    if "tarjouspyyntö" in normalized:
        return DocumentTypeGuess("rfq", ("rfq",))
    if "tarjous " in normalized or "urakoitsijan tarjous" in normalized:
        return DocumentTypeGuess("contractor_offer", ("contractor_offer",))
    if "työaikainen vakuus" in normalized or "vakuus" in normalized:
        return DocumentTypeGuess("security_document", ("security_document",))
    if "urakkaneuvottelu" in normalized or "liite1" in normalized:
        return DocumentTypeGuess("negotiation_minutes", ("negotiation_minutes",))
    if "sopimusehto" in normalized:
        return DocumentTypeGuess("contract_terms", ("contract_terms",))
    if "työturvallisuus" in normalized or "työsuojelu" in normalized:
        return DocumentTypeGuess("safety_plan", ("safety_plan",))
    if "aikataulu" in normalized:
        return DocumentTypeGuess("project_schedule", ("project_schedule",))
    if "toteutus" in normalized and "laadunhallinta" in normalized:
        return DocumentTypeGuess("quality_plan", ("quality_plan", "quality_manual"))
    if "urakoitsijan liitteet" in normalized:
        return DocumentTypeGuess("contractor_appendices", ("contractor_appendices",))
    if "liite5 ja 6" in normalized:
        return DocumentTypeGuess(
            "contractor_offer",
            ("contractor_offer", "unit_prices"),
            "Single PDF appears to contain both LIITE5 contractor offer and LIITE6 unit prices.",
        )
    if "laatukäsikirja" in normalized or "laatulaatukäsikirja" in normalized or "liite9" in normalized:
        return DocumentTypeGuess("quality_manual", ("quality_manual",))
    if "urakkasopimus" in normalized or "sukitusurakka" in normalized:
        return DocumentTypeGuess("main_contract", ("main_contract",))
    return DocumentTypeGuess("main_contract", ("main_contract",), "Document type needs manual review.")


def inspect_pdf(path: Path) -> tuple[int | None, bool | None, bool | None]:
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        sample_pages = reader.pages[: min(3, page_count)]
        sample_text = "\n".join((page.extract_text() or "") for page in sample_pages)
        has_text_layer = bool(sample_text.strip())
        needs_ocr = not has_text_layer
        return page_count, has_text_layer, needs_ocr
    except Exception:
        return None, None, None


def inventory(project_code: str, input_dir: Path, db_url: str) -> list[dict[str, object]]:
    pdf_files = sorted(input_dir.glob("*.pdf"), key=lambda item: item.name.casefold())
    rows: list[dict[str, object]] = []

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for path in pdf_files:
                guess = guess_document_type(path.name)
                page_count, has_text_layer, needs_ocr = inspect_pdf(path)
                file_hash = sha256_file(path)
                stored_path = path.as_posix()

                cur.execute(
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
                        stored_path,
                        guess.primary,
                        path.suffix.lower(),
                        file_hash,
                        page_count,
                        path.stat().st_size,
                        has_text_layer,
                        needs_ocr,
                        guess.notes,
                    ),
                )
                source_file_id = cur.fetchone()[0]
                cur.execute(
                    "DELETE FROM raw.source_file_document_types WHERE source_file_id = %s",
                    (source_file_id,),
                )

                for document_type in guess.all_types:
                    cur.execute(
                        """
                        INSERT INTO raw.source_file_document_types (
                            source_file_id, document_type, is_primary, notes
                        )
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (source_file_id, document_type) DO UPDATE
                        SET is_primary = EXCLUDED.is_primary,
                            notes = EXCLUDED.notes
                        """,
                        (
                            source_file_id,
                            document_type,
                            document_type == guess.primary,
                            guess.notes,
                        ),
                    )

                rows.append(
                    {
                        "filename": path.name,
                        "document_types": ", ".join(guess.all_types),
                        "page_count": page_count,
                        "byte_size": path.stat().st_size,
                        "has_text_layer": has_text_layer,
                        "needs_ocr": needs_ocr,
                        "sha256": file_hash,
                    }
                )
        conn.commit()
    return rows


def write_report(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Extraction Inventory",
        "",
        "| Filename | Document type(s) | Pages | Bytes | Text layer | Needs OCR | SHA256 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {filename} | {document_types} | {page_count} | {byte_size} | {has_text_layer} | {needs_ocr} | `{hash}` |".format(
                filename=row["filename"],
                document_types=row["document_types"],
                page_count=row["page_count"],
                byte_size=row["byte_size"],
                has_text_layer=row["has_text_layer"],
                needs_ocr=row["needs_ocr"],
                hash=str(row["sha256"])[:16],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    db_url = database_url(args.db, args.env)
    rows = inventory(args.project, args.input, db_url)
    write_report(args.report, rows)
    print(f"Inventoried {len(rows)} PDF files and wrote {args.report}")


if __name__ == "__main__":
    main()
