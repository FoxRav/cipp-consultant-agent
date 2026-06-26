from __future__ import annotations

import argparse
from pathlib import Path

from cipp_contracts.jsonio import write_json


def build_template(project_code: str) -> dict:
    return {
        "project_code": project_code,
        "project_type": "cipp_sukitusurakka",
        "property": {
            "property_code": "property_001",
            "city_redacted": "Kaupunki1",
            "building_year": None,
            "building_count": None,
            "stairwell_count": None,
            "apartment_count": None,
            "floor_area_m2": None,
            "floor_count": None,
        },
        "contract": {
            "contract_code": "contract_001",
            "contract_type": "construction_contract",
            "contract_date": None,
            "revision": None,
            "subject": "Viemärijärjestelmien CIPP-sukitusurakka",
            "standard_terms": "YSE 1998",
            "currency_code": "EUR",
        },
        "parties": [
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
                "display_name_redacted": "Suunnittelija1",
            },
        ],
        "documents": [
            {"document_type": "yse_1998", "attachment_no": None, "precedence_rank": 1},
            {"document_type": "main_contract", "attachment_no": None, "precedence_rank": 2},
            {"document_type": "negotiation_minutes", "attachment_no": "LIITE1", "precedence_rank": 5},
            {"document_type": "contract_terms", "attachment_no": "LIITE2", "precedence_rank": 9},
            {"document_type": "rfq", "attachment_no": "LIITE3", "precedence_rank": 3},
            {"document_type": "rfq_clarification", "attachment_no": "LIITE4", "precedence_rank": 10},
            {"document_type": "contractor_offer", "attachment_no": "LIITE5", "precedence_rank": 4},
            {"document_type": "unit_prices", "attachment_no": "LIITE6", "precedence_rank": 6},
            {"document_type": "payment_schedule", "attachment_no": "LIITE7", "precedence_rank": 7},
            {"document_type": "drawing_index", "attachment_no": "LIITE8", "precedence_rank": 8},
            {"document_type": "quality_manual", "attachment_no": "LIITE9", "precedence_rank": 11},
            {"document_type": "security_document", "attachment_no": None, "precedence_rank": 12},
        ],
        "scope_items": [],
        "boundaries": [],
        "technical_requirements": [],
        "responsibilities": [],
        "prices": [],
        "payment_schedule": [],
        "unit_prices": [],
        "securities": [],
        "insurances": [],
        "penalties": [],
        "quality_requirements": [],
        "deliverables": [],
        "clauses": [],
        "obligations": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    write_json(args.output, build_template(args.project))
    print(f"Wrote canonical template to {args.output}")


if __name__ == "__main__":
    main()
