from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RfqPropertyFacts:
    building_year: int | None
    building_count: int | None
    stairwell_count: int | None
    apartment_count: int | None
    floor_area_m2: Decimal | None
    floor_count: int | None
    metadata: dict[str, Any]


def parse_rfq_property_facts(project_label: str, text: str) -> RfqPropertyFacts:
    kohde = _kohde_section(text)
    building_year = _int_match(kohde, r"\bvm\.\s*(\d{4})")
    building_count = _building_count(kohde)
    stairwell_count = _int_match(kohde, r"Porrashuoneita\s+(\d+)")
    residential_apartments = _int_match(kohde, r"Asuntoja\s+(\d+)\s*kpl")
    if residential_apartments is None:
        residential_apartments = _int_match(kohde, r"(\d+)\s+asuntoa")
    house_count = _int_match(kohde, r"(\d+)\s+taloa")
    apartment_count = residential_apartments
    if apartment_count is None and house_count is not None and "erillistalo" in kohde.casefold():
        apartment_count = house_count

    commercial_units = _int_match(kohde, r"Liikehuoneistoja\s+(\d+)\s*kpl")
    other_units = _int_match(kohde, r"Muut\s+tilat\s+(\d+)\s*kpl")
    jv_vertical_count, jv_min, jv_max, jv_basis = _jv_vertical_count(kohde)
    sv_vertical_count = _sv_vertical_count(kohde)
    floor_area_m2 = _floor_area(kohde)
    floor_count = _floor_count(kohde)

    service_unit_count = _sum_present(apartment_count, commercial_units, other_units)
    metadata = {
        "project_label": project_label,
        "source_document_type": "rfq",
        "source_quote": _source_quote(kohde),
        "residential_apartment_count": residential_apartments,
        "commercial_unit_count": commercial_units,
        "other_space_count": other_units,
        "service_unit_count": service_unit_count,
        "jv_vertical_stack_count": jv_vertical_count,
        "sv_vertical_stack_count": sv_vertical_count,
        "data_confidence": "high",
    }
    if jv_min is not None:
        metadata["jv_vertical_stack_count_min"] = jv_min
        metadata["jv_vertical_stack_count_max"] = jv_max
        metadata["jv_vertical_stack_count_basis"] = jv_basis
        metadata["data_confidence"] = "medium_high"
    if "liikekiinteistö" in kohde.casefold() or commercial_units:
        metadata["reference_note"] = (
            "Mixed-use property; use service_unit_count for mixed-use comparisons "
            "and apartment_count for literal residential apartments."
        )

    return RfqPropertyFacts(
        building_year=building_year,
        building_count=building_count,
        stairwell_count=stairwell_count,
        apartment_count=apartment_count,
        floor_area_m2=floor_area_m2,
        floor_count=floor_count,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _kohde_section(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.replace("\u00ad", " "))
    match = re.search(r"\bKohde\b(.*?)(?:\bUrakan sisältö\b|\bTarjouksen sisältö\b)", compact, re.IGNORECASE)
    if match:
        return match.group(1)
    return compact


def _int_match(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _building_count(text: str) -> int | None:
    count = (
        _int_match(text, r"Rakennuksia\s+(\d+)")
        or _int_match(text, r"(\d+)\s+rakennus")
        or _int_match(text, r"(\d+)\s+taloa")
    )
    if count is None and "pienkerrostalo" in text.casefold():
        return 1
    return count


def _jv_vertical_count(text: str) -> tuple[int | None, int | None, int | None, str | None]:
    direct = _int_match(text, r"(?:JV\s+)?Pystyviemäreitä\s+(\d+)\s*kpl")
    if direct is not None:
        return direct, None, None, None

    per_house = re.search(
        r"Pystyviemäreitä\s+(\d+)\s*(?:[\-\u00ad\u2010-\u2015]\s*)+(\d+)\s*/\s*talo",
        text,
        re.IGNORECASE,
    )
    houses = _int_match(text, r"(\d+)\s+taloa")
    if per_house and houses:
        low_per_house, high_per_house = int(per_house.group(1)), int(per_house.group(2))
        low = low_per_house * houses
        high = high_per_house * houses
        return round((low + high) / 2), low, high, f"midpoint of {low_per_house}-{high_per_house} stacks per {houses} houses"

    formula = re.search(r"JV\s*(\d+)\s*\+\s*(\d+).*?JV\s*(\d+)", text, re.IGNORECASE)
    if formula:
        return sum(int(part) for part in formula.groups()), None, None, None
    return None, None, None, None


def _sv_vertical_count(text: str) -> int | None:
    return _int_match(text, r"SV\s*(\d+)")


def _floor_area(text: str) -> Decimal | None:
    area = _decimal_match(text, r"huoneistoala\s+([0-9]+(?:[,.][0-9]+)?)\s*m")
    if area is not None:
        return area
    areas = [
        value
        for value in (
            _decimal_match(text, r"Asuntoja\s+\d+\s*kpl,\s*([0-9]+(?:[,.][0-9]+)?)\s*m"),
            _decimal_match(text, r"Liikehuoneistoja\s+\d+\s*kpl,\s*([0-9]+(?:[,.][0-9]+)?)\s*m"),
            _decimal_match(text, r"Muut\s+tilat\s+\d+\s*kpl,\s*([0-9]+(?:[,.][0-9]+)?)\s*m"),
        )
        if value is not None
    ]
    if not areas:
        return None
    return sum(areas, Decimal("0"))


def _floor_count(text: str) -> int | None:
    if "yksikerroksisia" in text.casefold():
        return 1
    direct = _int_match(text, r"kerroksia\s+(\d+)")
    if direct is not None:
        return direct
    counts = [int(value) for value in re.findall(r"(\d+)\s*krs", text, re.IGNORECASE)]
    return max(counts) if counts else None


def _decimal_match(text: str, pattern: str) -> Decimal | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return Decimal(match.group(1).replace(",", "."))


def _sum_present(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _source_quote(kohde: str) -> str:
    return kohde.strip(" -•")[:700]
