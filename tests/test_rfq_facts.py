from pathlib import Path

import pytest

from cipp_contracts.normalize.rfq_facts import parse_rfq_property_facts


def _rfq(project: str) -> str:
    path = Path(f"data/extracted/{project}/markdown/rfq.md")
    if not path.exists():
        pytest.skip(f"RFQ fixture is not committed: {path}")
    return path.read_text(encoding="utf-8")


def test_parse_kapytie_rfq_facts() -> None:
    facts = parse_rfq_property_facts("Käpytie 15", _rfq("kapytie15"))

    assert facts.building_year == 1965
    assert facts.building_count == 1
    assert facts.apartment_count == 4
    assert facts.floor_area_m2 == 478
    assert facts.metadata["jv_vertical_stack_count"] == 5


def test_parse_lemmikkitie_rfq_facts() -> None:
    facts = parse_rfq_property_facts("Lemmikkitie 20", _rfq("lemmikkitie"))

    assert facts.building_year == 1968
    assert facts.building_count == 4
    assert facts.apartment_count == 4
    assert facts.floor_count == 1
    assert facts.metadata["jv_vertical_stack_count"] == 6
    assert facts.metadata["jv_vertical_stack_count_min"] == 4
    assert facts.metadata["jv_vertical_stack_count_max"] == 8


def test_parse_maakuntatalo_rfq_facts() -> None:
    facts = parse_rfq_property_facts("Maakuntatalo", _rfq("maakuntatalo"))

    assert facts.building_year == 1964
    assert facts.building_count == 2
    assert facts.apartment_count == 4
    assert facts.floor_area_m2 == 3746
    assert facts.floor_count == 7
    assert facts.metadata["service_unit_count"] == 33
    assert facts.metadata["jv_vertical_stack_count"] == 10
    assert facts.metadata["sv_vertical_stack_count"] == 2


def test_parse_tornanhovi_rfq_facts() -> None:
    facts = parse_rfq_property_facts("Tornanhovi", _rfq("tornanhovi"))

    assert facts.building_year == 1967
    assert facts.building_count == 1
    assert facts.stairwell_count == 3
    assert facts.apartment_count == 28
    assert facts.floor_area_m2 == 1791
    assert facts.floor_count == 3
    assert facts.metadata["service_unit_count"] == 30
    assert facts.metadata["jv_vertical_stack_count"] == 10
