from __future__ import annotations

from cipp_contracts.answer.cost_estimator import estimate_cost_from_packet


def test_cost_estimator_returns_structured_insufficient_result() -> None:
    result = estimate_cost_from_packet(
        {
            "user_case": {
                "apartments_count": 30,
                "buildings_count": 1,
                "staircases_count": 3,
                "jv_verticals_count": 15,
                "sv_verticals_count": 4,
                "roof_drains_count": 4,
                "bottom_drain_length_m": 50,
                "yard_line_length_m": 30,
                "stormwater_line_length_m": 30,
            },
            "kg_entities": [],
            "evidence": [],
        }
    )

    assert result["estimate_status"] == "insufficient_reference_data"
    assert result["estimate_low"] is None
    assert result["estimate_high"] is None
    assert result["estimate_currency"] == "EUR"
    assert result["case_used"]["apartments_count"] == 30
    assert result["reference_count"] == 0
    assert result["method"] == "reference_similarity_mvp"
    assert result["missing_inputs"]
    assert result["cost_drivers"]


def test_cost_estimator_uses_structured_finance_rows_only() -> None:
    result = estimate_cost_from_packet(
        {
            "user_case": {"apartments_count": 30},
            "kg_entities": [
                {"source_table": "finance.contract_prices", "metadata": {"contract_price": "100000"}},
                {"source_table": "finance.payment_schedule_items", "metadata": {"gross_total": "120000"}},
                {"source_table": "finance.unit_prices", "metadata": {"amount": "90000"}},
            ],
            "evidence": [{"source_table": "expert_guidance", "metadata": {"amount": "999999"}}],
        }
    )

    assert result["estimate_status"] == "estimated"
    assert result["estimate_low"] == 90000
    assert result["estimate_high"] == 120000
    assert result["reference_count"] == 3
