from __future__ import annotations

from decimal import Decimal

from cipp_contracts.normalize.report_reference_facts import (
    ReferenceFacts,
    calculate_price_per_apartment,
    determine_kg_readiness,
    next_blocker,
    payment_difference,
    payment_difference_pct,
    payment_matches,
    readiness_reasons,
    render_markdown,
    sum_payment_schedule_amounts,
)


def test_payment_schedule_total_match_logic() -> None:
    assert payment_matches(Decimal("1000.00"), Decimal("1000.50")) is True
    assert payment_matches(Decimal("1000.00"), Decimal("1003.00")) is False
    assert payment_matches(None, Decimal("1000.00")) is None


def test_payment_schedule_difference_fields_are_calculated() -> None:
    difference = payment_difference(Decimal("1000.00"), Decimal("1003.50"))

    assert difference == Decimal("3.50")
    assert payment_difference_pct(Decimal("1000.00"), difference) == Decimal("0.35")
    assert payment_difference(None, Decimal("1000.00")) is None
    assert payment_difference_pct(Decimal("0.00"), Decimal("1.00")) is None


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
    assert determine_kg_readiness("ok", [], ["payment_schedule_total"], None) == "needs_review"
    assert determine_kg_readiness("warning", [], [], True) == "ready"
    assert determine_kg_readiness("fail", [], [], True) == "not_ready"
    assert determine_kg_readiness("ok", ["contract_price"], [], None) == "not_ready"
    assert determine_kg_readiness("ok", [], ["contract_price"], True) == "needs_review"


def test_missing_payment_schedule_source_can_be_non_blocking() -> None:
    assert determine_kg_readiness("ok", [], [], None) == "ready"


def test_differing_payment_schedule_needs_review() -> None:
    assert determine_kg_readiness("ok", [], [], False) == "needs_review"


def test_ready_requires_blocking_evidence_to_be_clear() -> None:
    assert determine_kg_readiness("ok", [], ["contract_price"], True) == "needs_review"
    assert determine_kg_readiness("ok", ["contract_price"], [], True) == "not_ready"


def test_kg_readiness_reasons_explain_ready_and_review() -> None:
    ready = readiness_reasons("ok", [], [], True, "ready")
    review = readiness_reasons("ok", ["contract_price"], ["jv_scope_summary"], True, "needs_review")

    assert ready == ["all blocking facts have acceptable evidence"]
    assert "blocking missing fields: contract_price" in review
    assert "blocking weak evidence fields: jv_scope_summary" in review


def test_next_blocker_is_clear() -> None:
    assert next_blocker("fail", [], [], True) == "text_layer_status"
    assert next_blocker("ok", ["contract_price"], [], None) == "contract_price"
    assert next_blocker("ok", [], ["payment_schedule_total"], None) == "payment_schedule_total"
    assert (
        next_blocker("ok", [], [], False)
        == "payment_schedule_matches_contract_price"
    )
    assert next_blocker("ok", [], [], True) is None


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
            "payment_schedule_difference": "0.00",
            "payment_schedule_difference_pct": "0.00",
            "payment_schedule_evidence_status": "structured_and_matches",
            "payment_schedule_readiness_reason": "Structured payment schedule total matches.",
            "price_per_apartment": "10000.00",
            "missing_fields": "",
            "weak_evidence_fields": "",
            "blocking_missing_fields": "",
            "blocking_weak_evidence_fields": "",
            "next_blocker": "",
            "kg_readiness_reasons": "all blocking facts have acceptable evidence",
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
