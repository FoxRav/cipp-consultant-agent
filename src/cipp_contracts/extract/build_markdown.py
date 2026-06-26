from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+358|0)\s?(?:\d[\s-]?){6,12}(?!\d)")
BUSINESS_ID_RE = re.compile(r"\b\d{7}[-\u2010-\u2015]\d\b")
POSTAL_RE = re.compile(r"\b\d{5}\s+[A-ZÅÄÖ][A-ZÅÄÖa-zåäö -]+\b")
URL_RE = re.compile(r"\b(?:https?://)?(?:www\.)[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class Replacement:
    pattern: str
    replacement: str
    pii_type: str


PROJECT_REPLACEMENTS = [
    Replacement(r"\bReferenssikohde A\b", "Tilaaja1", "organization_name"),
    Replacement(r"\bPicote Oy Ltd\b", "Urakoitsija1", "organization_name"),
    Replacement(r"\bLTV\s+VIRTA\s+OY\b", "Valvoja1", "organization_name"),
    Replacement(r"\bLTV VIRTA OY\b", "Valvoja1", "organization_name"),
    Replacement(r"\bEtelä-Päijänteen OP-Kiinteistökeskus Oy\b", "Isännöitsijä1", "organization_name"),
    Replacement(r"\bSuoma Jokinen\b", "Henkilö1", "person_name"),
    Replacement(r"\bJoonas Sorvisto\b", "Henkilö2", "person_name"),
    Replacement(r"\bMarko Virta\b", "Henkilö3", "person_name"),
    Replacement(r"\bKasimir Hytönen\b", "Henkilö4", "person_name"),
    Replacement(r"\bPoutakatu 6\b", "Kohdeosoite1", "street_address"),
    Replacement(r"\bPalokärjentie 3\b", "Osoite1", "street_address"),
    Replacement(r"\bPalokärjentie\b", "Osoite1", "street_address"),
    Replacement(r"\bUrakoitsijantie 8\b", "Osoite2", "street_address"),
    Replacement(r"\bLahti\b", "Kaupunki1", "city"),
    Replacement(r"\bEspoo\b", "Kaupunki2", "city"),
    Replacement(r"\bPorvoo\b", "Kaupunki3", "city"),
    Replacement(r"\bVääksy\b", "Kaupunki4", "city"),
]


def redact_text(text: str) -> tuple[str, list[tuple[str, str]]]:
    findings: list[tuple[str, str]] = []
    redacted = text

    for replacement in PROJECT_REPLACEMENTS:
        redacted, count = re.subn(
            replacement.pattern,
            replacement.replacement,
            redacted,
            flags=re.IGNORECASE,
        )
        if count:
            findings.append((replacement.pii_type, replacement.replacement))

    for regex, placeholder, pii_type in (
        (EMAIL_RE, "[EMAIL_REDACTED]", "email"),
        (PHONE_RE, "[PHONE_REDACTED]", "phone"),
        (BUSINESS_ID_RE, "[BUSINESS_ID_REDACTED]", "business_id"),
        (POSTAL_RE, "[POSTAL_ADDRESS_REDACTED]", "postal_address"),
        (URL_RE, "[URL_REDACTED]", "url"),
    ):
        redacted, count = regex.subn(placeholder, redacted)
        if count:
            findings.append((pii_type, placeholder))

    return redacted, findings


def normalize_text(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\u00a0+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def build_markdown(project_code: str, output_dir: Path, db_url: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, original_filename, document_type
                FROM raw.source_files
                WHERE project_code = %s
                ORDER BY original_filename
                """,
                (project_code,),
            )
            source_files = cur.fetchall()

            for source_file in source_files:
                cur.execute(
                    "DELETE FROM audit.pii_findings WHERE source_file_id = %s",
                    (source_file["id"],),
                )
                cur.execute(
                    """
                    SELECT page_no, raw_text
                    FROM raw.pages
                    WHERE source_file_id = %s
                    ORDER BY page_no
                    """,
                    (source_file["id"],),
                )
                pages = cur.fetchall()
                if not pages:
                    continue

                parts = [
                    f"# {source_file['document_type']}",
                    "",
                    f"Source file: `{source_file['original_filename']}`",
                    "",
                ]
                all_findings: list[tuple[str, str]] = []
                for page in pages:
                    redacted, findings = redact_text(normalize_text(page["raw_text"] or ""))
                    all_findings.extend(findings)
                    parts.extend([f"## Page {page['page_no']}", "", redacted, ""])

                slug = source_file["document_type"]
                markdown_path = output_dir / f"{slug}.md"
                markdown_path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
                count += 1

                for pii_type, replacement in sorted(set(all_findings)):
                    cur.execute(
                        """
                        INSERT INTO audit.pii_findings (
                            source_file_id, location_text, pii_type, raw_value_hash,
                            replacement_value, visibility_decision
                        )
                        VALUES (%s,%s,%s, encode(digest(%s, 'sha256'), 'hex'), %s, 'redact')
                        """,
                        (
                            source_file["id"],
                            markdown_path.as_posix(),
                            pii_type,
                            replacement,
                            replacement,
                        ),
                    )

        conn.commit()

    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    count = build_markdown(args.project, args.output, database_url(args.db, args.env))
    print(f"Wrote {count} redacted markdown files")


if __name__ == "__main__":
    main()

