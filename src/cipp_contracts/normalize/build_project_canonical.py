from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url
from cipp_contracts.jsonio import write_json
from cipp_contracts.normalize.enrich_canonical_from_markdown import PRECEDENCE_RANKS

COMMON_DOCUMENT_TYPES = (
    "law_alueidenkayttolaki_132_1999",
    "law_rakentamislaki_751_2023",
    "yse_1998",
)

ATTACHMENT_BY_TYPE = {
    "negotiation_minutes": "LIITE1",
    "contract_terms": "LIITE2",
    "rfq": "LIITE3",
    "rfq_clarification": "LIITE4",
    "contractor_offer": "LIITE5",
    "unit_prices": "LIITE6",
    "payment_schedule": "LIITE7",
    "drawing_index": "LIITE8",
    "quality_manual": "LIITE9",
}

PROJECT_NAMES = {
    "pilot_001": "Kilpikoivu",
    "kapytie15": "Käpytie 15",
    "lemmikkitie": "Lemmikkitie 20",
    "maakuntatalo": "Maakuntatalo",
    "tornanhovi": "Tornanhovi",
}


def build(project_code: str, db_url: str, markdown_dir: Path) -> dict[str, Any]:
    documents = _documents_from_db(project_code, db_url)
    main_text = _read_markdown(markdown_dir / "main_contract.md")
    offer_text = _read_markdown(markdown_dir / "contractor_offer.md")
    note_text = _read_markdown(markdown_dir / "project_note.md")
    project_label = PROJECT_NAMES.get(project_code, project_code)

    contract_date = _first_date(main_text)
    revision = _first_match(main_text, r"\b(REV\d+)\b")
    contract_price = _contract_price(main_text)
    offer_price = _offer_price(offer_text)
    if contract_price and offer_price:
        for key in ("amount_net", "vat_amount", "amount_gross"):
            if contract_price.get(key) is None:
                contract_price[key] = offer_price.get(key)
    elif not contract_price:
        contract_price = offer_price

    combined_text = offer_text + "\n" + main_text
    return {
        "project_code": project_code,
        "project_name_redacted": f"Kohde_{project_code}",
        "project_type": "cipp_sukitusurakka",
        "property": {
            "property_code": f"property_{project_code}",
            "city_redacted": "Kaupunki1",
            "building_year": _int_after(offer_text + "\n" + main_text, r"Rakennusvuosi[: ]+(\d{4})"),
            "building_count": _int_after(offer_text, r"Rakennuksia[: ]+(\d+)"),
            "stairwell_count": _int_after(offer_text, r"Porraskäytäviä[: ]+(\d+)"),
            "apartment_count": _int_after(offer_text, r"Huoneistoja[: ]+(\d+)"),
            "floor_area_m2": None,
            "floor_count": _int_after(offer_text, r"Asuinkerroksia[: ]+(\d+)"),
            "metadata": {"project_label": project_label},
        },
        "contract": {
            "contract_code": "contract_001",
            "contract_type": "construction_contract",
            "contract_date": contract_date,
            "revision": revision,
            "subject": "Viemärijärjestelmien CIPP-sukitusurakka",
            "standard_terms": "YSE 1998",
            "currency_code": "EUR",
            "metadata": {
                "statutory_law_layer_rank": 0,
                "project_label": project_label,
                "source_document_type": "main_contract",
            },
        },
        "parties": _parties(project_code),
        "documents": documents,
        "scope_items": _scope_items(combined_text, note_text),
        "boundaries": _boundaries(main_text + "\n" + offer_text),
        "sewer_segments": _sewer_segments(combined_text, note_text),
        "technical_requirements": [],
        "responsibilities": [],
        "prices": [contract_price] if contract_price else [],
        "payment_schedule": [],
        "unit_prices": [],
        "securities": _securities(main_text),
        "insurances": [],
        "penalties": _penalties(main_text),
        "quality_requirements": [],
        "deliverables": [],
        "clauses": [],
        "obligations": [],
    }


def _documents_from_db(project_code: str, db_url: str) -> list[dict[str, Any]]:
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sf.original_filename, sf.page_count, m.document_type
                FROM raw.source_files sf
                JOIN raw.source_file_document_types m ON m.source_file_id = sf.id
                WHERE sf.project_code = %s
                ORDER BY sf.original_filename, m.document_type
                """,
                (project_code,),
            )
            project_rows = cur.fetchall()
            cur.execute(
                """
                SELECT sf.original_filename, sf.page_count, m.document_type
                FROM raw.source_files sf
                JOIN raw.source_file_document_types m ON m.source_file_id = sf.id
                WHERE m.document_type = ANY(%s)
                ORDER BY m.document_type
                """,
                (list(COMMON_DOCUMENT_TYPES),),
            )
            common_rows = cur.fetchall()

    by_type: dict[str, dict[str, Any]] = {}
    for row in list(common_rows) + list(project_rows):
        document_type = row["document_type"]
        by_type[document_type] = {
            "document_type": document_type,
            "document_title_redacted": document_type,
            "original_filename": row["original_filename"],
            "attachment_no": ATTACHMENT_BY_TYPE.get(document_type),
            "document_date": None,
            "page_count": row["page_count"],
            "precedence_rank": PRECEDENCE_RANKS.get(document_type, 99),
        }
    return sorted(by_type.values(), key=lambda item: (item["precedence_rank"], item["document_type"]))


def _read_markdown(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _first_date(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def _int_after(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _parse_euro(value: str) -> float:
    normalized = value.replace(" ", "").replace("\u00a0", "")
    normalized = re.sub(r"[^0-9,.]", "", normalized)
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "." in normalized:
        after_dot = normalized.rsplit(".", 1)[-1]
        if len(after_dot) == 3:
            normalized = normalized.replace(".", "")
    return float(normalized)


def _safe_parse_euro(value: str | None) -> float | None:
    if not value or not re.search(r"\d", value):
        return None
    try:
        return _parse_euro(value)
    except ValueError:
        return None


def _contract_price(text: str) -> dict[str, Any] | None:
    net = _first_match(text, r"Arvonlisäveroton urakkahinta:\s*(?:euroa)?\s*([0-9][0-9 ,.]*)(?:\s*€|\s*euroa)?")
    vat = _first_match(text, r"Arvonlisäveron osuus:\s*(?:euroa)?\s*([0-9][0-9 ,.]*)(?:\s*€|\s*euroa)?")
    gross = _first_match(text, r"Yhteensä:\s*(?:euroa)?\s*([0-9][0-9 ,.]*)(?:\s*€|\s*euroa)?")
    amount_gross = _safe_parse_euro(gross)
    if amount_gross is None:
        return None
    amount_net = _safe_parse_euro(net)
    vat_amount = _safe_parse_euro(vat)
    return {
        "price_type": "fixed_contract_price",
        "amount_net": amount_net,
        "vat_rate": 24,
        "vat_amount": vat_amount,
        "amount_gross": amount_gross,
        "currency_code": "EUR",
        "source_document_type": "main_contract",
    }


def _offer_price(text: str) -> dict[str, Any] | None:
    table_match = re.search(
        r"(?:Viemäreiden|Viemäreitten).*?sukitus\s+([0-9][0-9 .,\u00a0]*?)\s+([0-9][0-9 .,\u00a0]*?)\s+([0-9][0-9 .,\u00a0]*?)(?:\s|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if table_match:
        amount_net = _safe_parse_euro(table_match.group(1))
        vat_amount = _safe_parse_euro(table_match.group(2))
        amount_gross = _safe_parse_euro(table_match.group(3))
        if amount_gross is not None:
            return {
                "price_type": "fixed_contract_price",
                "amount_net": amount_net,
                "vat_rate": 24,
                "vat_amount": vat_amount,
                "amount_gross": amount_gross,
                "currency_code": "EUR",
                "source_document_type": "contractor_offer",
            }

    gross = _first_match(text, r"Hinta\s+([0-9][0-9 ,.]*)\s*€")
    net = _first_match(text, r"\)\s+([0-9][0-9 ,.]*)\s*€?\s*\(\s*alv\s*0")
    amount_gross = _safe_parse_euro(gross)
    if amount_gross is None:
        return None
    amount_net = _safe_parse_euro(net) or round(amount_gross / 1.24, 2)
    return {
        "price_type": "fixed_contract_price",
        "amount_net": amount_net,
        "vat_rate": 24,
        "vat_amount": round(amount_gross - amount_net, 2),
        "amount_gross": amount_gross,
        "currency_code": "EUR",
        "source_document_type": "contractor_offer",
    }


def _parties(project_code: str) -> list[dict[str, str]]:
    return [
        {"party_code": f"{project_code}_client", "party_type": "housing_company", "role": "client", "display_name_redacted": "Tilaaja1"},
        {"party_code": f"{project_code}_contractor", "party_type": "contractor", "role": "contractor", "display_name_redacted": "Urakoitsija1"},
        {"party_code": f"{project_code}_supervisor", "party_type": "consultant", "role": "supervisor", "display_name_redacted": "Valvoja1"},
    ]


def _scope_items(text: str, note_text: str = "") -> list[dict[str, Any]]:
    items = []
    if re.search(r"JV|jätevesi", text, re.IGNORECASE):
        items.append({"item_code": "scope_jv", "system_type": "JV", "item_name": "Jätevesiviemärit", "included_in_contract": True})
    if re.search(r"SV|sadevesi", text, re.IGNORECASE):
        items.append({"item_code": "scope_sv", "system_type": "SV", "item_name": "Sadevesiviemärit", "included_in_contract": True})
    if re.search(r"lattiakaivo", text, re.IGNORECASE):
        items.append({"item_code": "scope_floor_drains", "system_type": "floor_drain", "item_name": "Lattiakaivot", "included_in_contract": True})
    if "pohjaviemäri" in note_text.casefold() or "pohjaviemari" in note_text.casefold():
        items.append({"item_code": "scope_jv_base_excluded", "system_type": "JV", "item_name": "Pohjaviemäri", "included_in_contract": False, "notes": "Project note: excluded from contract"})
    if "tonttiviemäri" in note_text.casefold() or "tonttiviemari" in note_text.casefold():
        items.append({"item_code": "scope_plot_sewer_excluded", "system_type": "other", "item_name": "Tonttiviemäri", "included_in_contract": False, "notes": "Project note: excluded from contract"})
    return items


def _sewer_segments(text: str, note_text: str = "") -> list[dict[str, Any]]:
    folded = text.casefold()
    note_folded = note_text.casefold()
    has_jv = bool(re.search(r"\bJV\b|jätevesi|jätevesiviem|viemärilinja|viemäreiden sukitus|viemärien sukitus", text, re.IGNORECASE))
    has_sv = bool(re.search(r"\bSV\b|sadevesi|sadevesiviem", text, re.IGNORECASE))

    segments: list[dict[str, Any]] = []
    if has_jv:
        segments.extend(
            [
                _segment("JV", "apartment_branches", 1, "Asuntohajotukset", True, "Asuntokohtaiset viemärit liittyvät pystylinjoihin"),
                _segment("JV", "vertical_stacks", 2, "Pystylinjat", True, "Pystyviemärit, joihin asuntohajotukset liittyvät"),
                _segment("JV", "base_drain", 3, "Pohjaviemäri", _not_excluded(note_folded, "pohjaviem"), "Pystyviemärit liittyvät pohjaviemäriin"),
                _segment("JV", "plot_line", 4, "Tonttilinja", _not_excluded(note_folded, "tonttiviem"), "Pohjaviemäri liittyy tonttilinjaan"),
            ]
        )

    if has_sv:
        roof_collected = any(term in folded for term in ("katolla", "kattokaivo", "katto", "sv-pysty", "sv pysty"))
        yard_collected = any(term in folded for term in ("pihaviem", "pihalla", "tonttikaivo", "kaivo"))
        if yard_collected or not roof_collected:
            segments.extend(
                [
                    _segment("SV", "yard_drains", 1, "Pihamaan sadevesikaivot", True, "Sadevesi kerätään pihamaan kaivoista"),
                    _segment("SV", "plot_line", 2, "SV-tonttilinja", True, "Pihakaivoista vesi johdetaan maanalaista SV-tonttilinjaa pitkin kunnan linjalle", "lower_than_roof_collection"),
                ]
            )
        if roof_collected:
            segments.extend(
                [
                    _segment("SV", "roof_drains", 1, "Katon kerääjäkaivot", True, "Sadevesi kerätään myös katolta", "higher_due_to_roof_collection"),
                    _segment("SV", "vertical_stacks", 2, "SV-pystylinjat", True, "Katon sadevesi johdetaan SV-pystylinjoihin", "higher_due_to_roof_collection"),
                    _segment("SV", "base_drain", 3, "SV-pohjaviemäri", True, "SV-pystylinjat liittyvät SV-pohjaviemäriin", "higher_due_to_roof_collection"),
                ]
            )
    return _dedupe_segments(segments)


def _segment(
    system_type: str,
    segment_type: str,
    flow_order: int,
    segment_name: str,
    included: bool | None,
    boundary_text: str,
    pricing_impact: str | None = None,
) -> dict[str, Any]:
    return {
        "system_type": system_type,
        "segment_type": segment_type,
        "flow_order": flow_order,
        "segment_name": segment_name,
        "included_in_contract": included,
        "inclusion_confidence": 80 if included is not None else 40,
        "boundary_text": boundary_text,
        "pricing_impact": pricing_impact,
        "source_document_type": "main_contract",
    }


def _not_excluded(note_text: str, keyword: str) -> bool:
    return keyword not in note_text


def _dedupe_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for segment in segments:
        key = (segment["system_type"], segment["segment_type"])
        existing = by_key.get(key)
        if not existing or (not existing.get("included_in_contract") and segment.get("included_in_contract")):
            by_key[key] = segment
    return sorted(by_key.values(), key=lambda item: (item["system_type"], item["flow_order"], item["segment_type"]))


def _boundaries(text: str) -> list[dict[str, Any]]:
    boundaries = []
    if "tuuletusputkien" in text.casefold() or "tuuletusputkien päät" in text.casefold():
        boundaries.append({"system_type": "JV", "upstream_boundary": "Tuuletusputkien päät", "downstream_boundary": None})
    if "tarkastuskaivo" in text.casefold() or "tonttikaivo" in text.casefold():
        boundaries.append({"system_type": "JV", "upstream_boundary": None, "downstream_boundary": "Tarkastuskaivo tai tonttikaivo, tarkista lähdeasiakirjasta"})
    return boundaries


def _securities(text: str) -> list[dict[str, Any]]:
    rows = []
    construction = _first_match(text, r"rakennusaikaisen.*?määrältään:\s*([0-9 ][0-9 ,.]*)\s*euroa")
    warranty = _first_match(text, r"takuuajan.*?määrältään:\s*([0-9 ][0-9 ,.]*)\s*euroa")
    construction_amount = _safe_parse_euro(construction)
    warranty_amount = _safe_parse_euro(warranty)
    if construction_amount is not None:
        rows.append({"security_type": "construction_period", "amount": construction_amount, "basis": "Source: main_contract", "issuer_role": "contractor", "beneficiary_role": "client"})
    if warranty_amount is not None:
        rows.append({"security_type": "warranty_period", "amount": warranty_amount, "basis": "Source: main_contract", "issuer_role": "contractor", "beneficiary_role": "client"})
    return rows


def _penalties(text: str) -> list[dict[str, Any]]:
    if "viivästyssakko" not in text.casefold():
        return []
    percent = _first_match(text, r"(\d+,\d+|\d+\.\d+|\d+)\s*%\s*arvonlisäverottomasta")
    max_days = _first_match(text, r"enintään\s+(\d+)\s+työpäiv")
    return [
        {
            "penalty_type": "delay_penalty",
            "percent_per_workday": _parse_euro(percent) if percent else None,
            "max_workdays": int(max_days) if max_days else None,
            "basis": "Arvonlisäveroton urakkahinta",
            "calculation_text": "Poimittu pääsopimuksesta; tarkista clause-kerroksesta",
        }
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--markdown-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    data = build(args.project, database_url(args.db, args.env), args.markdown_dir)
    write_json(args.output, data)
    print(f"Wrote project canonical JSON to {args.output}")


if __name__ == "__main__":
    main()
