from __future__ import annotations

import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from cipp_contracts.config import database_url

AKN_NS = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}


@dataclass(frozen=True)
class LawMapping:
    filename: str
    document_type: str
    title: str
    law_number: str


LAW_MAPPINGS = {
    "rakentamislaki_751_2023.xml": LawMapping(
        "rakentamislaki_751_2023.xml",
        "law_rakentamislaki_751_2023",
        "Rakentamislaki 751/2023",
        "751/2023",
    ),
    "alueidenkayttolaki_132_1999.xml": LawMapping(
        "alueidenkayttolaki_132_1999.xml",
        "law_alueidenkayttolaki_132_1999",
        "Alueidenkäyttölaki / maankäyttö- ja rakennuslaki 132/1999",
        "132/1999",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def child_text(element: ET.Element, tag: str) -> str:
    child = element.find(f"akn:{tag}", AKN_NS)
    if child is None:
        return ""
    return clean_text(" ".join(child.itertext()))


def section_text(section: ET.Element) -> str:
    parts: list[str] = []
    for child in list(section):
        local_name = child.tag.split("}", 1)[-1]
        if local_name in {"num", "heading"}:
            continue
        text = clean_text(" ".join(child.itertext()))
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def parse_law(path: Path) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()
    title_element = root.find(".//akn:docTitle", AKN_NS)
    title = clean_text(" ".join(title_element.itertext())) if title_element is not None else ""
    produced = ""
    issued = ""
    published = ""
    for item in root.findall(".//akn:FRBRdate", AKN_NS):
        name = item.attrib.get("name")
        if name == "dateProduced":
            produced = item.attrib.get("date", "")
        elif name == "dateIssued":
            issued = item.attrib.get("date", "")
        elif name == "datePublished":
            published = item.attrib.get("date", "")

    sections = []
    for index, section in enumerate(root.findall(".//akn:section", AKN_NS), start=1):
        num = child_text(section, "num")
        heading = child_text(section, "heading")
        body = section_text(section)
        if not num and not heading and not body:
            continue
        sections.append(
            {
                "order": index,
                "eid": section.attrib.get("eId"),
                "num": num,
                "heading": heading,
                "body": body,
            }
        )

    return {
        "title": title,
        "issued": issued,
        "published": published,
        "produced": produced,
        "sections": sections,
    }


def import_legal_xml(project_code: str, input_dir: Path, markdown_dir: Path, db_url: str) -> int:
    markdown_dir.mkdir(parents=True, exist_ok=True)
    imported = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for path in sorted(input_dir.glob("*.xml")):
                mapping = LAW_MAPPINGS.get(path.name)
                if not mapping:
                    continue
                parsed = parse_law(path)
                file_hash = sha256_file(path)

                cur.execute(
                    """
                    INSERT INTO raw.source_files (
                        project_code, original_filename, stored_path, document_type,
                        file_ext, sha256, page_count, byte_size, has_text_layer, needs_ocr, notes
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
                        mapping.document_type,
                        ".xml",
                        file_hash,
                        len(parsed["sections"]),
                        path.stat().st_size,
                        True,
                        False,
                        f"Finlex AKN XML; sections={len(parsed['sections'])}; produced={parsed['produced']}",
                    ),
                )
                source_file_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO raw.source_file_document_types (
                        source_file_id, document_type, is_primary, notes
                    )
                    VALUES (%s,%s,true,%s)
                    ON CONFLICT (source_file_id, document_type) DO UPDATE
                    SET is_primary = true,
                        notes = EXCLUDED.notes
                    """,
                    (
                        source_file_id,
                        mapping.document_type,
                        f"{mapping.title}; Finlex produced {parsed['produced']}",
                    ),
                )

                markdown_path = markdown_dir / f"{mapping.document_type}.md"
                markdown_path.write_text(build_markdown(mapping, parsed), encoding="utf-8")
                imported += 1
        conn.commit()

    return imported


def build_markdown(mapping: LawMapping, parsed: dict[str, Any]) -> str:
    lines = [
        f"# {mapping.title}",
        "",
        f"Document type: `{mapping.document_type}`",
        f"Law number: `{mapping.law_number}`",
        f"Issued: `{parsed['issued']}`",
        f"Published: `{parsed['published']}`",
        f"Finlex produced: `{parsed['produced']}`",
        "",
    ]
    for section in parsed["sections"]:
        title = " ".join(part for part in [section["num"], section["heading"]] if part)
        lines.extend(
            [
                f"## {title}",
                "",
                f"AKN eId: `{section['eid']}`",
                "",
                section["body"],
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    count = import_legal_xml(
        args.project,
        args.input,
        args.markdown_output,
        database_url(args.db, args.env),
    )
    print(f"Imported {count} Finlex XML law files")


if __name__ == "__main__":
    main()
