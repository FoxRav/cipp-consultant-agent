from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pypdf import PdfReader

from cipp_contracts.config import database_url


MIGRATION_PATH = Path(__file__).resolve().parents[3] / "db" / "migrations" / "009_legal_guidance_documents.sql"
DOCUMENT_TYPE = "legal_guidance_pipe_renovation"
PROJECT_CODE = "legal_guidance"
SOURCE_TYPE = "expert_guidance"
AUTHORITY_LEVEL = "non_binding_guidance"
BINDING_STATUS = "not_binding_law"
LEGAL_ROLE = "planning_and_decision_guidance"
USER_FACING_ROLE = "taloyhtiön hallituksen ja osakkaan ohjaava asiantuntija-aineisto"
EXTRACTION_METHOD = "rules_first_guidance_pdf_v0.6"

PROCESS_STAGES = {
    "property_strategy": ("kiinteistönpidon strategia", "strategia", "korjausohjelma"),
    "condition_monitoring": ("kunnon seuranta", "seuranta"),
    "needs_assessment": ("kunnossapitotarveselvitys", "tarveselvitys", "korjaustarve"),
    "condition_survey": ("kuntotutkimus", "koejyrsintä", "koerassaus", "kunnon arviointi"),
    "method_selection": ("korjausvaihtoehto", "pinnoitus", "sukitus", "sukkasujutus", "hybridi"),
    "project_planning": ("hankesuunnittelu", "hankesuunnitelma"),
    "design": ("suunnittelu", "suunnittelija"),
    "procurement": ("tarjouspyyntö", "urakoitsijoiden kartoitus", "tarjoukset"),
    "contracting": ("urakkaneuvottelu", "urakkasopimus", "sopimus"),
    "construction": ("rakentaminen", "huoneistokohtaiset työt", "aloituskokous", "työmaa"),
    "supervision": ("valvonta", "valvoja", "työmaakokous"),
    "handover": ("loppukatselmus", "vastaanottotarkastus", "vastaanotto", "luovutus"),
    "warranty": ("takuuaika", "takuutarkastus", "takuu"),
    "cost_reporting": ("taloudellinen loppuselvitys", "kustannusselvitys", "kustannukset"),
}

TOPIC_CODES = {
    "maintenance_strategy": ("strategia", "korjausohjelma", "kiinteistönpito"),
    "maintenance_need": ("kunnossapitotarve", "korjaustarve", "tarveselvitys"),
    "pipe_lifetime": ("käyttöikä", "keskimääräinen käyttöikä"),
    "water_pipe_condition": ("käyttövesiputkisto", "käyttövesiputki"),
    "sewer_condition": ("viemäriputkisto", "viemäri", "jätevesi"),
    "condition_survey": ("kuntotutkimus", "kunnon arviointi"),
    "test_milling": ("koejyrsintä", "koerassaus"),
    "repair_options": ("korjausvaihtoehto", "uusiminen"),
    "coating": ("pinnoitus", "pinnoittaminen"),
    "cipp_lining": ("sukitus", "sukkasujutus", "sujutus"),
    "hybrid_solution": ("hybridi", "hybridiratkaisu"),
    "project_governance": ("hanke", "projektinjohto", "hallinta"),
    "housing_company_decision": ("yhtiökokous", "hankepäätös", "rakentamispäätös", "hyväksyttäminen"),
    "shareholder_information": ("osakas", "tiedotustilaisuus", "tiedottaminen"),
    "design_procurement": ("suunnittelijoiden valinta", "suunnittelun hankinta"),
    "contractor_procurement": ("urakoitsijoiden kartoitus", "tarjouspyyntö", "urakoitsija"),
    "contract_negotiation": ("urakkaneuvottelu", "urakkasopimus"),
    "safety_coordination": ("turvallisuuskoordinaattori", "turvallisuus"),
    "moisture_management": ("kosteudenhallinta", "kosteudenhallintaselvitys"),
    "supervision": ("valvonta", "valvoja"),
    "handover": ("vastaanotto", "loppukatselmus"),
    "financial_final_account": ("taloudellinen loppuselvitys",),
    "warranty": ("takuu", "takuutarkastus"),
    "cost_statement": ("kustannusselvitys",),
}

ACTORS = {
    "housing_company": ("taloyhtiö", "yhtiö"),
    "board": ("hallitus", "hallituksen"),
    "shareholders": ("osakas", "osakkaat", "osakkaille"),
    "property_manager": ("isännöitsijä",),
    "designer": ("suunnittelija", "suunnittelijat"),
    "supervisor": ("valvoja",),
    "contractor": ("urakoitsija", "urakoitsijat"),
    "safety_coordinator": ("turvallisuuskoordinaattori",),
    "project_manager": ("projektinjohtaja", "projektipäällikkö"),
    "resident": ("asukas", "asukkaat"),
}

GUIDANCE_SIGNALS = (
    "tulee",
    "pitää",
    "on syytä",
    "kannattaa",
    "suositellaan",
    "edellyttää",
    "voidaan joutua",
    "on varmistettava",
    "on nimettävä",
    "päätetään",
    "hyväksytään",
    "liitetään",
    "tehdään yhtiökokouksessa",
    "riski",
    "haitta",
    "varauduttava",
    "ei voida",
    "ei sovellu",
    "soveltuu",
    "edellytykset",
)

LEGAL_REFERENCES = {
    "tietoyhteiskuntakaari 917/2014": "tietoyhteiskuntakaari_917_2014",
    "valtioneuvoston asetus rakennuksen esteettömyydestä 241/2017": "esteettomyysasetus_241_2017",
    "rakennustyön turvallisuusasetus 205/2009": "rakennustyon_turvallisuusasetus_205_2009",
    "ympäristöministeriön asetus rakennusten kosteusteknisestä toimivuudesta 782/2017": "kosteustekninen_toimivuus_782_2017",
}

KNOWN_SECTIONS = (
    ("1", "Johdanto", ("johdanto", "kiinteistönpidon strategia", "hankepäätös")),
    ("2", "Putkiston keskimääräiset käyttöiät", ("käyttöiät", "käyttöikä", "putkiston keskimääräiset")),
    ("3", "Rakennuksen putkiston kunnon arviointi", ("kunnon arviointi", "kuntotutkimus", "koejyrsintä")),
    ("4", "Korjausvaihtoehdot", ("korjausvaihtoehdot", "pinnoitus", "sukkasujutus", "hybridi")),
    ("5", "Taloyhtiön korjaushanke pähkinänkuoressa", ("korjaushanke pähkinänkuoressa", "hankesuunnittelu", "vastaanottotarkastus")),
)


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    text: str


@dataclass(frozen=True)
class GuidanceSection:
    section_number: str
    title: str
    page_start: int
    page_end: int
    text_hash: str


@dataclass(frozen=True)
class GuidanceItem:
    item_type: str
    topic_code: str | None
    process_stage: str | None
    actor: str
    guidance_summary: str
    legal_relevance: str
    binding_status: str
    page_number: int
    section_ref: str
    confidence: float
    metadata: dict[str, Any]


def ensure_schema(conn: psycopg.Connection[Any]) -> None:
    conn.execute(MIGRATION_PATH.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_pdf_pages(path: Path) -> list[ParsedPage]:
    reader = PdfReader(str(path))
    pages: list[ParsedPage] = []
    for index, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        pages.append(ParsedPage(index, text))
    return pages


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ0-9])", text)
    return [clean_text(part) for part in parts if clean_text(part)]


def identify_sections(pages: list[ParsedPage]) -> list[GuidanceSection]:
    starts: list[tuple[str, str, int]] = []
    for page in pages:
        normalized = page.text.lower()
        for number, title, markers in KNOWN_SECTIONS:
            if any(marker in normalized for marker in markers) and number not in {item[0] for item in starts}:
                starts.append((number, title, page.page_no))
    if not starts and pages:
        starts.append(("1", "Taloyhtiön putkiremonttiopas", pages[0].page_no))
    starts.sort(key=lambda item: item[2])
    sections: list[GuidanceSection] = []
    for index, (number, title, page_start) in enumerate(starts):
        next_start = starts[index + 1][2] if index + 1 < len(starts) else pages[-1].page_no + 1
        page_end = max(page_start, next_start - 1)
        section_text = " ".join(page.text for page in pages if page_start <= page.page_no <= page_end)
        sections.append(GuidanceSection(number, title, page_start, page_end, hashlib.sha256(section_text.encode()).hexdigest()))
    return sections


def section_for_page(sections: list[GuidanceSection], page_no: int) -> GuidanceSection | None:
    for section in sections:
        if section.page_start <= page_no <= section.page_end:
            return section
    return sections[0] if sections else None


def extract_guidance_items(pages: list[ParsedPage], sections: list[GuidanceSection]) -> list[GuidanceItem]:
    items: list[GuidanceItem] = []
    seen: set[tuple[int, str]] = set()
    for page in pages:
        section = section_for_page(sections, page.page_no)
        section_ref = f"{section.section_number} {section.title}" if section else ""
        for sentence in sentence_split(page.text):
            normalized = sentence.lower()
            legal_refs = detect_legal_references(normalized)
            has_signal = any(signal in normalized for signal in GUIDANCE_SIGNALS)
            if not has_signal and not legal_refs:
                continue
            summary = summarize_sentence(sentence)
            if len(summary) < 30:
                continue
            dedupe_key = (page.page_no, summary)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            item_type = classify_item_type(normalized, legal_refs)
            items.append(
                GuidanceItem(
                    item_type=item_type,
                    topic_code=classify_topic(normalized, section_ref),
                    process_stage=classify_stage(normalized, section_ref),
                    actor=classify_actor(normalized),
                    guidance_summary=summary,
                    legal_relevance=legal_relevance(normalized, legal_refs),
                    binding_status=BINDING_STATUS,
                    page_number=page.page_no,
                    section_ref=section_ref,
                    confidence=confidence_for_item(normalized, legal_refs),
                    metadata={
                        "extraction_method": EXTRACTION_METHOD,
                        "signals": [signal for signal in GUIDANCE_SIGNALS if signal in normalized],
                        "legal_references": legal_refs,
                    },
                )
            )
    return items


def summarize_sentence(sentence: str, max_length: int = 420) -> str:
    text = clean_text(sentence)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def classify_item_type(text: str, legal_refs: list[str]) -> str:
    if legal_refs:
        return "legal_cross_reference"
    if any(word in text for word in ("riski", "haitta", "varauduttava", "ei sovellu", "ei voida")):
        return "risk_warning"
    if any(word in text for word in ("päätetään", "hyväksytään", "yhtiökokouksessa", "hankepäätös")):
        return "decision_point"
    if any(word in text for word in ("soveltuu", "edellytykset", "pinnoitus", "sukitus", "sukkasujutus")):
        return "method_condition"
    if any(word in text for word in ("vastaanotto", "takuutarkastus", "takuuaika")):
        return "warranty_or_handover_note"
    if any(word in text for word in ("tarkastus", "katselmus", "valvonta")):
        return "inspection_requirement"
    if any(word in text for word in ("tarjouspyyntö", "sopimus", "liitetään", "asiakirja")):
        return "document_requirement"
    if any(word in text for word in ("hallitus", "isännöitsijä", "suunnittelija", "valvoja", "urakoitsija")):
        return "actor_responsibility"
    if any(word in text for word in ("hankesuunnittelu", "suunnittelu", "rakentaminen")):
        return "project_stage"
    if any(word in text for word in ("tulee", "pitää", "kannattaa", "on syytä", "suositellaan")):
        return "checklist_item"
    return "principle"


def classify_stage(text: str, section_ref: str = "") -> str | None:
    haystack = f"{text} {section_ref.lower()}"
    for code, markers in PROCESS_STAGES.items():
        if any(marker in haystack for marker in markers):
            return code
    return None


def classify_topic(text: str, section_ref: str = "") -> str | None:
    haystack = f"{text} {section_ref.lower()}"
    for code, markers in TOPIC_CODES.items():
        if any(marker in haystack for marker in markers):
            return code
    return None


def classify_actor(text: str) -> str:
    for code, markers in ACTORS.items():
        if any(marker in text for marker in markers):
            return code
    return "unknown"


def detect_legal_references(text: str) -> list[str]:
    result: list[str] = []
    for label, code in LEGAL_REFERENCES.items():
        label_lower = label.lower()
        number = code.rsplit("_", 2)[-2] + "/" + code.rsplit("_", 1)[-1] if "_" in code else ""
        if label_lower in text or (number and number in text):
            result.append(code)
    return result


def legal_relevance(text: str, legal_refs: list[str]) -> str:
    if legal_refs:
        return "Mentions a legal source; cross-reference status is mentioned_not_verified until linked to binding law."
    if "edellyttää" in text:
        return "Guidance uses stronger wording, but remains non-binding unless verified from binding law or contract."
    return "Non-binding expert guidance for planning, decisions, or checks."


def confidence_for_item(text: str, legal_refs: list[str]) -> float:
    if legal_refs:
        return 0.95
    if any(signal in text for signal in ("tulee", "pitää", "on varmistettava", "on nimettävä")):
        return 0.9
    if any(signal in text for signal in ("kannattaa", "on syytä", "suositellaan")):
        return 0.85
    return 0.75


def register_source_file(conn: psycopg.Connection[Any], path: Path, page_count: int) -> str:
    file_hash = sha256_file(path)
    row = conn.execute(
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
            page_count = EXCLUDED.page_count,
            byte_size = EXCLUDED.byte_size,
            has_text_layer = EXCLUDED.has_text_layer,
            needs_ocr = EXCLUDED.needs_ocr,
            notes = EXCLUDED.notes
        RETURNING id
        """,
        (
            PROJECT_CODE,
            path.name,
            path.as_posix(),
            DOCUMENT_TYPE,
            ".pdf",
            file_hash,
            page_count,
            path.stat().st_size,
            True,
            False,
            "Expert guidance; non-binding law-grade planning guidance.",
        ),
    ).fetchone()
    source_file_id = str(row["id"])
    conn.execute(
        """
        INSERT INTO raw.source_file_document_types (source_file_id, document_type, is_primary, notes)
        VALUES (%s,%s,true,%s)
        ON CONFLICT (source_file_id, document_type) DO UPDATE
        SET is_primary = true,
            notes = EXCLUDED.notes
        """,
        (source_file_id, DOCUMENT_TYPE, "Legal guidance document; not binding law."),
    )
    return source_file_id


def upsert_pages(conn: psycopg.Connection[Any], source_file_id: str, pages: list[ParsedPage]) -> dict[int, str]:
    run_id = conn.execute(
        """
        INSERT INTO raw.extraction_runs (
            source_file_id, extractor_name, extractor_version, status, config, extraction_finished_at
        )
        VALUES (%s,%s,%s,'completed',%s,now())
        RETURNING id
        """,
        (source_file_id, "pypdf", "rules_first_guidance_pdf_v0.6", Jsonb({"document_type": DOCUMENT_TYPE})),
    ).fetchone()["id"]
    page_ids: dict[int, str] = {}
    for page in pages:
        row = conn.execute(
            """
            INSERT INTO raw.pages (
                source_file_id, extraction_run_id, page_no, raw_text, raw_text_hash, text_quality_score
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source_file_id, page_no) DO UPDATE
            SET extraction_run_id = EXCLUDED.extraction_run_id,
                raw_text = EXCLUDED.raw_text,
                raw_text_hash = EXCLUDED.raw_text_hash,
                text_quality_score = EXCLUDED.text_quality_score
            RETURNING id
            """,
            (
                source_file_id,
                run_id,
                page.page_no,
                page.text,
                hashlib.sha256(page.text.encode()).hexdigest(),
                text_quality(page.text),
            ),
        ).fetchone()
        page_ids[page.page_no] = str(row["id"])
    return page_ids


def text_quality(text: str) -> float:
    if not text:
        return 0.0
    alpha = sum(1 for char in text if char.isalpha())
    return round(min(1.0, alpha / max(len(text), 1)) * 100, 2)


def upsert_guidance_document(
    conn: psycopg.Connection[Any],
    *,
    document_code: str,
    title: str,
    author: str | None,
    publisher: str | None,
    publication_year: int | None,
    edition: str | None,
    source_file_id: str,
) -> str:
    row = conn.execute(
        """
        INSERT INTO legal.guidance_documents (
            document_code, title, author, publisher, edition, publication_year,
            source_type, authority_level, binding_status, legal_role, user_facing_role,
            requires_cross_reference, source_file_id, metadata
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s)
        ON CONFLICT (document_code) DO UPDATE
        SET title = EXCLUDED.title,
            author = EXCLUDED.author,
            publisher = EXCLUDED.publisher,
            edition = EXCLUDED.edition,
            publication_year = EXCLUDED.publication_year,
            source_type = EXCLUDED.source_type,
            authority_level = EXCLUDED.authority_level,
            binding_status = EXCLUDED.binding_status,
            legal_role = EXCLUDED.legal_role,
            user_facing_role = EXCLUDED.user_facing_role,
            requires_cross_reference = EXCLUDED.requires_cross_reference,
            source_file_id = EXCLUDED.source_file_id,
            metadata = EXCLUDED.metadata,
            updated_at = now()
        RETURNING id
        """,
        (
            document_code,
            title,
            author,
            publisher,
            edition,
            publication_year,
            SOURCE_TYPE,
            AUTHORITY_LEVEL,
            BINDING_STATUS,
            LEGAL_ROLE,
            USER_FACING_ROLE,
            source_file_id,
            Jsonb({"copyright_sensitive": True, "use_as": "checklist_and_process_guidance"}),
        ),
    ).fetchone()
    return str(row["id"])


def prune_guidance(conn: psycopg.Connection[Any], document_id: str) -> None:
    conn.execute("DELETE FROM legal.guidance_sections WHERE guidance_document_id = %s", (document_id,))


def upsert_sections(
    conn: psycopg.Connection[Any],
    guidance_document_id: str,
    sections: list[GuidanceSection],
) -> dict[str, str]:
    section_ids: dict[str, str] = {}
    for section in sections:
        row = conn.execute(
            """
            INSERT INTO legal.guidance_sections (
                guidance_document_id, section_number, title, page_start, page_end, text_hash, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (guidance_document_id, section_number, title, page_start) DO UPDATE
            SET page_end = EXCLUDED.page_end,
                text_hash = EXCLUDED.text_hash,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                guidance_document_id,
                section.section_number,
                section.title,
                section.page_start,
                section.page_end,
                section.text_hash,
                Jsonb({"extraction_method": EXTRACTION_METHOD}),
            ),
        ).fetchone()
        section_ids[section.section_number] = str(row["id"])
    return section_ids


def upsert_items(
    conn: psycopg.Connection[Any],
    guidance_document_id: str,
    sections: list[GuidanceSection],
    section_ids: dict[str, str],
    page_ids: dict[int, str],
    source_file_id: str,
    items: list[GuidanceItem],
) -> int:
    written = 0
    for item in items:
        section = section_for_page(sections, item.page_number)
        section_id = section_ids.get(section.section_number) if section else None
        conn.execute(
            """
            INSERT INTO legal.guidance_items (
                guidance_document_id, section_id, item_type, topic_code, process_stage, actor,
                guidance_summary, legal_relevance, binding_status, confidence,
                page_number, source_file_id, page_id, section_ref, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (guidance_document_id, page_number, section_ref, item_type, guidance_summary)
            DO UPDATE
            SET section_id = EXCLUDED.section_id,
                topic_code = EXCLUDED.topic_code,
                process_stage = EXCLUDED.process_stage,
                actor = EXCLUDED.actor,
                legal_relevance = EXCLUDED.legal_relevance,
                binding_status = EXCLUDED.binding_status,
                confidence = EXCLUDED.confidence,
                source_file_id = EXCLUDED.source_file_id,
                page_id = EXCLUDED.page_id,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            (
                guidance_document_id,
                section_id,
                item.item_type,
                item.topic_code,
                item.process_stage,
                item.actor,
                item.guidance_summary,
                item.legal_relevance,
                item.binding_status,
                item.confidence,
                item.page_number,
                source_file_id,
                page_ids.get(item.page_number),
                item.section_ref,
                Jsonb(item.metadata),
            ),
        )
        written += 1
    return written


def build_report(
    *,
    document_code: str,
    pages: list[ParsedPage],
    sections: list[GuidanceSection],
    items: list[GuidanceItem],
    dry_run: bool,
) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    by_topic: dict[str, int] = {}
    legal_cross_refs = 0
    for item in items:
        by_type[item.item_type] = by_type.get(item.item_type, 0) + 1
        if item.process_stage:
            by_stage[item.process_stage] = by_stage.get(item.process_stage, 0) + 1
        if item.topic_code:
            by_topic[item.topic_code] = by_topic.get(item.topic_code, 0) + 1
        if item.item_type == "legal_cross_reference":
            legal_cross_refs += 1
    return {
        "document_code": document_code,
        "source_type": SOURCE_TYPE,
        "authority_level": AUTHORITY_LEVEL,
        "binding_status": BINDING_STATUS,
        "legal_role": LEGAL_ROLE,
        "dry_run": dry_run,
        "pages": len(pages),
        "sections": len(sections),
        "guidance_items": len(items),
        "legal_cross_references": legal_cross_refs,
        "by_item_type": dict(sorted(by_type.items())),
        "by_process_stage": dict(sorted(by_stage.items())),
        "by_topic_code": dict(sorted(by_topic.items())),
    }


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Legal Guidance Import Report",
        "",
        f"- Document code: `{report['document_code']}`",
        f"- Source type: `{report['source_type']}`",
        f"- Authority level: `{report['authority_level']}`",
        f"- Binding status: `{report['binding_status']}`",
        f"- Dry run: `{str(report['dry_run']).lower()}`",
        f"- Pages: {report['pages']}",
        f"- Sections: {report['sections']}",
        f"- Guidance items: {report['guidance_items']}",
        f"- Legal cross-references: {report['legal_cross_references']}",
        "",
        "## Item Types",
        "",
        *_dict_lines(report["by_item_type"]),
        "",
        "## Process Stages",
        "",
        *_dict_lines(report["by_process_stage"]),
        "",
        "## Topics",
        "",
        *_dict_lines(report["by_topic_code"]),
        "",
        "This report intentionally excludes long source text from the copyrighted guide.",
    ]
    return "\n".join(lines)


def _dict_lines(values: dict[str, int]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- `{key}`: {value}" for key, value in values.items()]


def write_report(report: dict[str, Any], output: Path | None, output_md: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_report_markdown(report) + "\n", encoding="utf-8")


def import_guidance_pdf(
    *,
    db_url: str,
    file: Path,
    document_code: str,
    title: str,
    author: str | None,
    publisher: str | None,
    publication_year: int | None,
    edition: str | None,
    dry_run: bool = False,
    prune_existing: bool = False,
) -> dict[str, Any]:
    pages = parse_pdf_pages(file)
    sections = identify_sections(pages)
    items = extract_guidance_items(pages, sections)
    report = build_report(document_code=document_code, pages=pages, sections=sections, items=items, dry_run=dry_run)
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        ensure_schema(conn)
        source_file_id = register_source_file(conn, file, len(pages))
        page_ids = upsert_pages(conn, source_file_id, pages)
        document_id = upsert_guidance_document(
            conn,
            document_code=document_code,
            title=title,
            author=author,
            publisher=publisher,
            publication_year=publication_year,
            edition=edition,
            source_file_id=source_file_id,
        )
        if prune_existing:
            prune_guidance(conn, document_id)
        section_ids = upsert_sections(conn, document_id, sections)
        upsert_items(conn, document_id, sections, section_ids, page_ids, source_file_id, items)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--document-code", required=True)
    parser.add_argument("--title", default="Taloyhtiön putkiremonttiopas")
    parser.add_argument("--author")
    parser.add_argument("--publisher")
    parser.add_argument("--publication-year", type=int)
    parser.add_argument("--edition")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune-existing", action="store_true")
    parser.add_argument("--output-report", type=Path)
    parser.add_argument("--output-report-md", type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    report = import_guidance_pdf(
        db_url=database_url(args.db, args.env),
        file=args.file,
        document_code=args.document_code,
        title=args.title,
        author=args.author,
        publisher=args.publisher,
        publication_year=args.publication_year,
        edition=args.edition,
        dry_run=args.dry_run,
        prune_existing=args.prune_existing,
    )
    write_report(report, args.output_report, args.output_report_md)
    print(
        json.dumps(
            {
                "document_code": report["document_code"],
                "pages": report["pages"],
                "sections": report["sections"],
                "guidance_items": report["guidance_items"],
                "binding_status": report["binding_status"],
                "dry_run": report["dry_run"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
