from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url
from cipp_contracts.jsonio import read_json, write_json


DOCUMENT_DATES = {
    "law_rakentamislaki_751_2023": "2023-04-21",
    "law_alueidenkayttolaki_132_1999": "1999-02-05",
    "yse_1998": "1998-03-01",
    "main_contract": "2015-11-25",
    "rfq": "2015-05-06",
    "contractor_offer": "2015-07-02",
    "negotiation_minutes": "2015-08-06",
    "unit_prices": "2015-07-02",
    "payment_schedule": "2015-09-28",
    "drawing_index": "2015-09-28",
    "contract_terms": "2015-05-06",
    "rfq_clarification": "2015-05-27",
    "quality_manual": None,
    "security_document": "2016-02-12",
    "attachment_index": None,
    "negotiation_attachment": None,
    "safety_plan": None,
    "project_schedule": None,
    "contractor_appendices": None,
    "quality_plan": None,
    "project_note": None,
}

PRECEDENCE_RANKS = {
    "law_rakentamislaki_751_2023": 0,
    "law_alueidenkayttolaki_132_1999": 0,
    "yse_1998": 1,
    "main_contract": 2,
    "rfq": 3,
    "contractor_offer": 4,
    "negotiation_minutes": 5,
    "unit_prices": 6,
    "payment_schedule": 7,
    "drawing_index": 8,
    "contract_terms": 9,
    "rfq_clarification": 10,
    "quality_manual": 11,
    "security_document": 12,
    "quality_plan": 13,
    "safety_plan": 14,
    "project_schedule": 15,
    "attachment_index": 16,
    "negotiation_attachment": 17,
    "contractor_appendices": 18,
    "project_note": 99,
}


def enrich(data: dict[str, Any], db_url: str, project_code: str) -> dict[str, Any]:
    data["project_code"] = project_code
    data["project_name_redacted"] = "Kohde1"
    data["project_type"] = "cipp_sukitusurakka"
    data["property"] = {
        "property_code": "property_001",
        "city_redacted": "Kaupunki1",
        "building_year": 1968,
        "building_count": 2,
        "stairwell_count": 5,
        "apartment_count": 49,
        "floor_area_m2": None,
        "floor_count": 3,
    }
    data["contract"] = {
        "contract_code": "contract_001",
        "contract_type": "construction_contract",
        "contract_date": "2015-11-25",
        "revision": "REV5",
        "subject": "Viemärijärjestelmien CIPP-sukitusurakka",
        "standard_terms": "YSE 1998",
        "currency_code": "EUR",
        "metadata": {
            "source_document_type": "main_contract",
            "source_page": 1,
        "contract_document_list_mentions_yse_1998_as_rank_1": True,
            "statutory_law_layer_rank": 0,
        },
    }
    data["parties"] = [
        {
            "party_code": "client_001",
            "party_type": "housing_company",
            "role": "client",
            "display_name_redacted": "Tilaaja1",
        },
        {
            "party_code": "contractor_001",
            "party_type": "contractor",
            "role": "contractor",
            "display_name_redacted": "Urakoitsija1",
        },
        {
            "party_code": "supervisor_001",
            "party_type": "consultant",
            "role": "supervisor",
            "display_name_redacted": "Valvoja1",
        },
        {
            "party_code": "designer_001",
            "party_type": "consultant",
            "role": "designer",
            "display_name_redacted": "Valvoja1",
        },
        {
            "party_code": "property_manager_001",
            "party_type": "property_manager",
            "role": "property_manager",
            "display_name_redacted": "Isännöitsijä1",
        },
    ]
    data["documents"] = _documents_from_db(db_url, project_code)
    data["boundaries"] = [
        {
            "system_type": "JV",
            "upstream_boundary": "Tuuletusputkien päät",
            "downstream_boundary": "Tonttikaivo nro 3, katselmoitu",
            "source_document_type": "main_contract",
            "source_page": 1,
        },
        {
            "system_type": "SV",
            "upstream_boundary": "Ylin tonttikaivo",
            "downstream_boundary": "Tonttikaivo nro 3, katselmoitu",
            "source_document_type": "main_contract",
            "source_page": 1,
        },
    ]
    data["sewer_segments"] = [
        {"system_type": "JV", "segment_type": "apartment_branches", "flow_order": 1, "segment_name": "Asuntohajotukset", "included_in_contract": True, "inclusion_confidence": 90, "boundary_text": "Asuntokohtaiset viemärit liittyvät pystylinjoihin", "source_document_type": "main_contract"},
        {"system_type": "JV", "segment_type": "vertical_stacks", "flow_order": 2, "segment_name": "Pystylinjat", "included_in_contract": True, "inclusion_confidence": 90, "boundary_text": "15 JV-pystylinjaa", "source_document_type": "payment_schedule"},
        {"system_type": "JV", "segment_type": "base_drain", "flow_order": 3, "segment_name": "Pohjaviemäri", "included_in_contract": True, "inclusion_confidence": 80, "boundary_text": "Maksuerätaulukossa mainitaan kaikki JV-pohjaviemärit", "source_document_type": "payment_schedule"},
        {"system_type": "JV", "segment_type": "plot_line", "flow_order": 4, "segment_name": "Tonttilinja", "included_in_contract": True, "inclusion_confidence": 80, "boundary_text": "Alajuoksulla tonttikaivo nro 3, katselmoitu", "source_document_type": "main_contract"},
        {"system_type": "SV", "segment_type": "yard_drains", "flow_order": 1, "segment_name": "Pihamaan sadevesikaivot", "included_in_contract": True, "inclusion_confidence": 80, "boundary_text": "Sadevesilinjojen urakkaraja yläjuoksulla ylin tonttikaivo", "pricing_impact": "lower_than_roof_collection", "source_document_type": "main_contract"},
        {"system_type": "SV", "segment_type": "plot_line", "flow_order": 2, "segment_name": "SV-tonttilinja", "included_in_contract": True, "inclusion_confidence": 80, "boundary_text": "Alajuoksulla tonttikaivo nro 3, katselmoitu", "pricing_impact": "lower_than_roof_collection", "source_document_type": "main_contract"},
    ]
    data["scope_items"] = [
        {"item_code": "scope_jv_all", "system_type": "JV", "item_name": "Kaikki jätevesiviemäriputket", "included_in_contract": True},
        {"item_code": "scope_sv_all", "system_type": "SV", "item_name": "Kaikki sadevesiviemäriputket", "included_in_contract": True},
        {"item_code": "scope_jv_verticals", "system_type": "JV", "item_name": "15 JV-pystylinjaa", "included_in_contract": True},
        {"item_code": "scope_floor_drains", "system_type": "floor_drain", "item_name": "Lattiakaivojen kunnostus", "included_in_contract": True},
    ]
    data["prices"] = [
        {
            "price_type": "fixed_contract_price",
            "amount_net": 225806.45,
            "vat_rate": 24,
            "vat_amount": 54193.55,
            "amount_gross": 280000.00,
            "currency_code": "EUR",
            "source_document_type": "main_contract",
            "source_page": 5,
        }
    ]
    data["payment_schedule"] = _payment_schedule()
    data["unit_prices"] = _unit_prices()
    data["securities"] = [
        {
            "security_type": "construction_period",
            "amount": 22500.00,
            "amount_percent": 10,
            "basis": "ALV0 urakkahinta",
            "validity_text": "Voimassa kolme kuukautta hyväksytyn valmistumisajan yli",
            "issuer_role": "contractor",
            "beneficiary_role": "client",
            "source_document_type": "main_contract",
            "source_page": 5,
        },
        {
            "security_type": "warranty_period",
            "amount": 5000.00,
            "amount_percent": 2,
            "basis": "ALV0 urakkahinta",
            "validity_text": "Voimassa kolme kuukautta yli takuuajan",
            "issuer_role": "contractor",
            "beneficiary_role": "client",
            "source_document_type": "main_contract",
            "source_page": 5,
        },
    ]
    data["insurances"] = [
        {
            "insurance_type": "construction_work_insurance",
            "required_by_role": "contractor",
            "coverage_amount": 220000.00,
            "coverage_text": "Rakennustyövakuutus kattaa urakkasopimuksen kohteena olevan suorituksen",
            "source_document_type": "main_contract",
            "source_page": 5,
        },
        {
            "insurance_type": "liability_insurance",
            "required_by_role": "contractor",
            "coverage_amount": 1000000.00,
            "coverage_text": "Toiminnan vastuuvakuutus vähintään 1M€",
            "source_document_type": "main_contract",
            "source_page": 5,
        },
    ]
    data["penalties"] = [
        {
            "penalty_type": "delay_penalty",
            "percent_per_workday": 0.1,
            "max_workdays": 50,
            "basis": "Arvonlisäveroton urakkahinta",
            "calculation_text": "0,1 % ALV0-urakkahinnasta kultakin työpäivältä, enintään 50 työpäivältä",
            "source_document_type": "main_contract",
            "source_page": 4,
        }
    ]
    data["responsibilities"] = _responsibilities()
    data["technical_requirements"] = _technical_requirements()
    data["deliverables"] = _deliverables()
    data["quality_requirements"] = _quality_requirements()
    data["schedule_milestones"] = [
        {"milestone_key": "start_right", "milestone_name": "Oikeus aloittaa työt", "planned_date": "2016-02-01", "source_page": 4},
        {"milestone_key": "latest_start", "milestone_name": "Viimeinen aloituspäivä", "planned_date": "2016-02-08", "source_page": 4},
        {"milestone_key": "operational_completion", "milestone_name": "Operatiivinen valmistuminen", "planned_date": "2016-05-27", "qualifier": "operatiivisin osin", "source_page": 4},
    ]
    return data


def _documents_from_db(db_url: str, project_code: str) -> list[dict[str, Any]]:
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sf.original_filename, sf.page_count, sf.document_type, m.document_type AS mapped_type
                FROM raw.source_files sf
                JOIN raw.source_file_document_types m ON m.source_file_id = sf.id
                WHERE sf.project_code = %s
                ORDER BY sf.original_filename, m.document_type
                """,
                (project_code,),
            )
            rows = cur.fetchall()

    docs = []
    for row in sorted(rows, key=lambda item: PRECEDENCE_RANKS[item["mapped_type"]]):
        document_type = row["mapped_type"]
        docs.append(
            {
                "document_type": document_type,
                "document_title_redacted": document_type,
                "original_filename": row["original_filename"],
                "attachment_no": _attachment_no(document_type),
                "document_date": DOCUMENT_DATES.get(document_type),
                "page_count": row["page_count"],
                "precedence_rank": PRECEDENCE_RANKS[document_type],
            }
        )
    return docs


def _attachment_no(document_type: str) -> str | None:
    mapping = {
        "law_rakentamislaki_751_2023": None,
        "law_alueidenkayttolaki_132_1999": None,
        "yse_1998": None,
        "negotiation_minutes": "LIITE1",
        "contract_terms": "LIITE2",
        "rfq": "LIITE3",
        "rfq_clarification": "LIITE4",
        "contractor_offer": "LIITE5",
        "unit_prices": "LIITE6",
        "payment_schedule": "LIITE7",
        "drawing_index": "LIITE8",
        "quality_manual": "LIITE9",
        "security_document": None,
    }
    return mapping.get(document_type)


def _payment_schedule() -> list[dict[str, Any]]:
    net_values = [22580.65] + [18064.52] * 10 + [22580.65]
    gross_values = [28000.00] + [22400.00] * 10 + [28000.00]
    conditions = [
        "Kun urakkasopimus on allekirjoitettu, rakennusaikainen vakuus on toimitettu ja työmaa perustettu",
        "Kun 2 pystylinjaa ja kaikki siihen liittyvät asunnot on tehty",
        "Kun 4 pystylinjaa ja kaikki siihen liittyvät asunnot on tehty",
        "Kun 6 pystylinjaa ja kaikki siihen liittyvät asunnot on tehty",
        "Kun 8 pystylinjaa ja kaikki siihen liittyvät asunnot on tehty",
        "Kun 10 pystylinjaa ja kaikki siihen liittyvät asunnot on tehty",
        "Kun 12 pystylinjaa ja kaikki siihen liittyvät asunnot on tehty",
        "Kun kaikki 15 pystylinjaa ja niihin liittyvät asunnot on tehty",
        "Kun kaikki SV-viemärit on tehty",
        "Kun kaikki JV-pohjaviemärit on tehty",
        "Kun 100 %, kaikki operatiivinen työ on tehty",
        "Kun kaikki loppuasiakirjat on toimitettu ja takuuajan vakuus asetettu",
    ]
    return [
        {
            "item_no": index,
            "amount_net": net,
            "vat_rate": 24,
            "vat_amount": round(gross - net, 2),
            "amount_gross": gross,
            "payment_condition": condition,
            "source_document_type": "payment_schedule",
            "source_page": 1,
        }
        for index, (net, gross, condition) in enumerate(zip(net_values, gross_values, conditions), start=1)
    ]


def _unit_prices() -> list[dict[str, Any]]:
    rows = [
        ("up_001", "WC-istuin IDO Seven D 37213-01 (saneerausjalallinen)", "kpl", 395.00),
        ("up_002", "Valurautaisen hajulukon vaihtaminen muoviseksi", "kpl", 185.00),
        ("up_003", "Padotusventtiilin vaihto DN100, muovi", "kpl", 1700.00),
        ("up_004", "Padotusventtiilin vaihto DN100, valurauta", "kpl", 2500.00),
        ("up_005", "WC-viemärin sukitus", "kpl", 185.00),
        ("up_006", "Pesualtaan viemärin sukitus", "kpl", 185.00),
        ("up_007", "Lattiakaivon pinnoitus ja viemärin sukitus", "kpl", 300.00),
        ("up_008", "Lattiakaivon pinnoitus", "kpl", 125.00),
        ("up_009", "Keittiön viemärin sukitus", "kpl", 185.00),
    ]
    return [
        {
            "unit_price_code": code,
            "item_name": name,
            "unit": unit,
            "amount_gross": gross,
            "vat_rate": 24,
            "condition_text": "Hinnat viemäröintipisteestä pystyviemäriin tai toisen viemärin liittymään lattiassa",
            "source_document_type": "unit_prices",
            "source_page": 4,
        }
        for code, name, unit, gross in rows
    ]


def _responsibilities() -> list[dict[str, str]]:
    rows = [
        ("temporary_structures", "Työnaikaiset rakennelmat ja telineet", "contractor", "Urakoitsija"),
        ("access_routes", "Kulkuteiden tekeminen ja kunnossapito", "contractor", "Urakoitsija"),
        ("work_area", "Työsuoritusta varten tarpeellisen alueen osoittaminen", "client", "Tilaaja osoittaa alueen"),
        ("site_security", "Rakennuskohteen vartiointi", "contractor", "Urakoitsija vastaa omista välineistä ja työkaluista"),
        ("protection", "Rakennuskohteen, rakennusosien, tarvikkeiden ja ympäristön suojaaminen", "contractor", "Urakoitsija"),
        ("waste_management", "Työmaan sisäinen jätehuolto ja siivous", "contractor", "Urakoitsija omien töidensä osalta"),
        ("social_spaces", "Sosiaali-, varasto-, toimisto- ja työskentelytilat", "contractor", "Tilaaja osoittaa tilan, urakoitsija varustaa"),
        ("water_electricity", "Vesi, valaistus ja sähkö", "client", "Tilaaja antaa veden ja sähkön"),
        ("keys", "Yleisavain ja huoltoavain", "client", "Tilaaja luovuttaa yleisavaimen; urakoitsija vastaa katoamisesta"),
        ("subcontractors", "Aliurakoitsijoiden hyväksyttäminen", "contractor", "Hyväksytetään erikseen tilaajalla"),
        ("communication", "Tiedotusvastuu hankkeen aikana", "contractor", "Urakoitsija vastaa tiedotuksesta ensitiedotetta lukuun ottamatta"),
        ("kvv_inspection", "KVV-tarkastus", "contractor", "Urakoitsija toimittaa omalla kustannuksellaan"),
    ]
    return [
        {
            "responsibility_key": key,
            "responsibility_area": area,
            "responsible_role": role,
            "details": details,
            "source_document_type": "main_contract" if key not in {"communication", "kvv_inspection"} else "contract_terms",
        }
        for key, area, role, details in rows
    ]


def _technical_requirements() -> list[dict[str, Any]]:
    return [
        {"requirement_code": "tech_iso_11296_4", "requirement_type": "standard", "requirement_text": "Urakassa noudatetaan kansainvälistä ISO 11296-4 -standardia", "standard_ref": "ISO 11296-4", "source_document_type": "contract_terms", "source_page": 1},
        {"requirement_code": "tech_wrinkle_2mm", "requirement_type": "acceptance_limit", "requirement_text": "Haarayhdekohtien rypyt tai muut häiriöt eivät saa ylittää 2 mm", "numeric_limit": 2, "unit": "mm", "source_document_type": "contract_terms", "source_page": 1},
        {"requirement_code": "tech_branch_total_4mm", "requirement_type": "acceptance_limit", "requirement_text": "Haarayhteen kokonaispaksuus on korkeintaan 4 mm", "numeric_limit": 4, "unit": "mm", "source_document_type": "contract_terms", "source_page": 1},
        {"requirement_code": "tech_pipe_size_50mm", "requirement_type": "scope_rule", "requirement_text": "Kaikki 50 mm putket ja sitä isommat koot sukitetaan", "numeric_limit": 50, "unit": "mm", "source_document_type": "contract_terms", "source_page": 1},
        {"requirement_code": "tech_water_analysis", "requirement_type": "inspection", "requirement_text": "Valmiit sukitetut linjat kuvataan veden juostessa vesianalyysillä", "source_document_type": "contract_terms", "source_page": 1},
    ]


def _quality_requirements() -> list[dict[str, str]]:
    return [
        {"requirement_key": "qr_video_approval", "requirement_category": "payment_readiness", "requirement_text": "Maksueriä ei lähetetä ennen kuin osa-alueen videot on hyväksytty valvojan toimesta ja mahdolliset vastinelausunnot saatu urakoitsijalta", "evidence_required": "Luovutusvideot ja valvojan hyväksyntä"},
        {"requirement_key": "qr_self_handover", "requirement_category": "handover", "requirement_text": "Urakoitsija toimittaa itselleluovutuksen ennen varsinaista kohteen luovutusta", "evidence_required": "Itselleluovutusasiakirja"},
        {"requirement_key": "qr_worksite_diary", "requirement_category": "documentation", "requirement_text": "Työmaapäiväkirja päivitetään pilvipalveluun vähintään 3 kertaa viikossa", "evidence_required": "Työmaapäiväkirja"},
    ]


def _deliverables() -> list[dict[str, str]]:
    names = [
        "Sopimus, tarjous ja maksuerätaulukko",
        "Taloudellinen loppuselvitys",
        "Työmaakokouspöytäkirjat",
        "Asukastyytyväisyyskysely",
        "Vastaanottoasiakirjat",
        "RATU- tai työmaapäiväkirjakopiot",
        "Käyttöturvallisuustiedote, katkaisuohje, sertifikaatti tai RT-kortti",
        "Huoltotakuu tai selvitys ongelmatilanteiden toimintatavasta",
        "Takuuajan vakuuden kopio",
        "Tarkepiirustukset",
    ]
    return [
        {
            "deliverable_key": f"deliverable_{index:03d}",
            "deliverable_name": name,
            "required_at": "Luovutuskansio",
            "required_by_role": "contractor",
            "source_document_type": "contract_terms",
            "source_page": 3,
        }
        for index, name in enumerate(names, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    data = enrich(read_json(args.input), database_url(args.db, args.env), args.project)
    write_json(args.output, data)
    print(f"Wrote enriched canonical JSON to {args.output}")


if __name__ == "__main__":
    main()
