from __future__ import annotations

from decimal import Decimal
from statistics import median
from typing import Any


CASE_FIELDS = (
    "apartments_count",
    "buildings_count",
    "staircases_count",
    "jv_verticals_count",
    "sv_verticals_count",
    "roof_drains_count",
    "bottom_drain_length_m",
    "yard_line_length_m",
    "stormwater_line_length_m",
)

COST_DRIVER_POINTS = (
    "Asuntojen määrä vaikuttaa toistuvien asuntohajotus- ja pystylinjatöiden kokonaislaajuuteen.",
    "JV-pystyviemäreiden määrä vaikuttaa linjakohtaiseen työmäärään, aikatauluun ja asukashaittaan.",
    "SV-pystyviemärit ja kattokaivot voivat kasvattaa kustannusta, jos sadevesi kerätään katolta sisäisiä linjoja pitkin.",
    "Pohjaviemärin pituus vaikuttaa alajuoksun työmäärään ja työmaan järjestelyihin.",
    "Tonttilinjan pituus ja liittymäkohta vaikuttavat urakkarajoihin ja maarakennus-/kaivotöihin.",
    "Sadevesilinjojen pituus ja kaivojen määrä pitää erottaa JV-laajuudesta.",
    "Rakennusten ja porrashuoneiden määrä vaikuttavat vaiheistukseen ja logistiikkaan.",
    "Urakkarajat ratkaisevat, mitä hintaan saa sisällyttää ja mitä pitää hinnoitella erikseen.",
)

REQUIRED_INPUTS = (
    "urakkarajat",
    "kuuluuko käyttövesi mukaan",
    "sukitetaanko vain viemärit",
    "kylpyhuoneiden / lattiakaivojen määrä",
    "tonttilinjan todellinen pituus",
    "pohjaviemärin todellinen pituus",
    "sadevesilinjojen todellinen pituus",
    "kaivojen määrä",
    "laadunvarmistusvaatimukset",
    "suunnitelmien taso",
)

STRUCTURED_PRICE_TABLES = {
    "finance.contract_prices",
    "finance.payment_schedule_items",
    "finance.unit_prices",
    "reference_facts_matrix",
}


def estimate_cost_from_packet(packet: dict[str, Any]) -> dict[str, Any]:
    case_used = {field: packet.get("user_case", {}).get(field) for field in CASE_FIELDS}
    prices = structured_price_values(packet)
    if len(prices) >= 3:
        low = min(prices)
        high = max(prices)
        midpoint = median(prices)
        return {
            "estimate_status": "estimated",
            "estimate_low": int(low),
            "estimate_high": int(high),
            "estimate_midpoint": int(midpoint),
            "estimate_currency": "EUR",
            "basis": [
                f"Perustuu {len(prices)} anonymisoituun rakenteiseen hintariviin.",
                "Menetelmä on alustava min-max-haarukka saatavilla olevista referensseistä.",
            ],
            "case_used": case_used,
            "cost_drivers": list(COST_DRIVER_POINTS),
            "missing_inputs": missing_inputs(case_used),
            "warnings": ["ALV-statusta ei varmisteta tässä MVP-arviossa, ellei lähdedata sisällä sitä erikseen."],
            "reference_count": len(prices),
            "method": "reference_similarity_mvp",
        }
    return {
        "estimate_status": "insufficient_reference_data",
        "estimate_low": None,
        "estimate_high": None,
        "estimate_midpoint": None,
        "estimate_currency": "EUR",
        "basis": [
            "Rakenteista ja anonymisoitua hintadataa ei ole vielä riittävästi luotettavaan euromääräiseen haarukkaan."
        ],
        "case_used": case_used,
        "cost_drivers": list(COST_DRIVER_POINTS),
        "missing_inputs": missing_inputs(case_used),
        "warnings": [
            "Euromäärää ei muodosteta ilman vähintään kolmea käyttökelpoista rakenteista referenssihintaa.",
            "Asiantuntijaohjeita voidaan käyttää prosessihuomioihin, mutta ei hintalaskennan pohjaksi.",
        ],
        "reference_count": len(prices),
        "method": "reference_similarity_mvp",
    }


def structured_price_values(packet: dict[str, Any]) -> list[Decimal]:
    values: list[Decimal] = []
    for row_group in ("kg_entities", "evidence"):
        for row in packet.get(row_group) or []:
            if row.get("source_table") not in STRUCTURED_PRICE_TABLES:
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            for key in ("contract_price", "gross_total", "net_total", "price", "amount", "value"):
                amount = decimal_or_none(metadata.get(key) if metadata else row.get(key))
                if amount is not None and amount > 0:
                    values.append(amount)
    return values


def missing_inputs(case_used: dict[str, Any]) -> list[str]:
    missing = list(REQUIRED_INPUTS)
    for field, label in (
        ("apartments_count", "asuntojen määrä"),
        ("jv_verticals_count", "JV-pystyviemäreiden määrä"),
        ("sv_verticals_count", "SV-pystyviemäreiden määrä"),
        ("roof_drains_count", "kattokaivojen määrä"),
        ("bottom_drain_length_m", "pohjaviemärin pituus"),
        ("yard_line_length_m", "tonttilinjan pituus"),
        ("stormwater_line_length_m", "sadevesilinjojen pituus"),
    ):
        if case_used.get(field) in (None, ""):
            missing.append(label)
    return list(dict.fromkeys(missing))


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return None
