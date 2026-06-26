from __future__ import annotations

from decimal import Decimal

from cipp_contracts.normalize.report_reference_facts import (
    ReferenceFacts,
    calculate_price_per_apartment,
    determine_kg_readiness,
    payment_matches,
    render_markdown,
    sum_payment_schedule_amounts,
)


def test_payment_schedule_total_match_logic() -> None:
    assert payment_matches(Decimal("1000.00"), Decimal("1000.50")) is True
    assert payment_matches(Decimal("1000.00"), Decimal("1003.00")) is False
    assert payment_matches(None, Decimal("1000.00")) is None


def test_price_per_apartment_is_calculated() -> None:
    assert calculate_price_per_apartment(Decimal("100000.00"), 20) == Decimal("5000.00")
    assert calculate_price_per_apartment(None, 20) is None
    assert calculate_price_per_apartment(Decimal("100000.00"), None) is None


def test_payment_schedule_total_is_calculated_from_gross_or_net() -> None:
    items = [
        {"amount_gross": Decimal("100.00"), "amount_net": Decimal("80.00")},
        {"amount_gross": None, "amount_net": Decimal("50.00")},
    ]

    assert sum_payment_schedule_amounts(items) == Decimal("150.00")


def test_kg_readiness_ready_needs_review_and_not_ready() -> None:
    assert determine_kg_readiness("ok", [], [], True) == "ready"
    assert determine_kg_readiness("ok", ["payment_schedule_total"], [], None) == "needs_review"
    assert determine_kg_readiness("warning", [], [], True) == "needs_review"
    assert determine_kg_readiness("fail", [], [], True) == "not_ready"
    assert determine_kg_readiness("ok", ["apartments_count", "contract_price"], [], None) == "not_ready"


def test_render_markdown_contains_fixture_project_and_evidence() -> None:
    facts = ReferenceFacts(
        values={
            "project_code": "reference_test",
            "project_display_name": "Reference Test",
            "source_coverage_status": "ok",
            "text_layer_status": "ok",
            "apartments_count": 10,
            "contract_price": "100000.00",
            "payment_schedule_total": "100000.00",
            "payment_schedule_matches_contract_price": True,
            "price_per_apartment": "10000.00",
            "missing_fields": "",
            "weak_evidence_fields": "",
            "confidence_summary": "strong",
            "kg_readiness_status": "ready",
        },
        evidence=[
            {
                "field_name": "contract_price",
                "value": "100000.00",
                "source_table": "finance.contract_prices",
                "source_column": "amount_gross",
                "confidence": "high",
            }
        ],
    )

    markdown = render_markdown([facts])

    assert "reference_test" in markdown
    assert "kg_readiness_status" in markdown
    assert "finance.contract_prices" in markdown


def test_missing_fields_are_represented_in_fixture_fact() -> None:
    facts = ReferenceFacts(
        values={
            "project_code": "missing_fixture",
            "missing_fields": "apartments_count, contract_price",
            "weak_evidence_fields": "",
            "kg_readiness_status": "not_ready",
        },
        missing_fields=["apartments_count", "contract_price"],
    )

    assert "apartments_count" in facts.values["missing_fields"]
    assert facts.values["kg_readiness_status"] == "not_ready"
