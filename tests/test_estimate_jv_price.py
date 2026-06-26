from decimal import Decimal

from cipp_contracts.price.estimate_jv_price import ReferenceProject, estimate_jv_price


def test_kilpikoivu_reference_estimate_matches_default() -> None:
    estimate = estimate_jv_price(apartment_count=49)

    assert estimate.reference_project_code == "pilot_001"
    assert estimate.estimated_price_gross == Decimal("280000.00")
    assert estimate.estimated_price_per_apartment_gross == Decimal("5714.29")
    assert estimate.weighted_multiplier == Decimal("1.0000")


def test_small_building_moves_toward_high_per_apartment_price() -> None:
    estimate = estimate_jv_price(apartment_count=10)

    assert estimate.estimated_price_per_apartment_gross == Decimal("8000.00")
    assert estimate.low_price_gross == Decimal("50000.00")
    assert estimate.high_price_gross == Decimal("80000.00")


def test_closest_internal_reference_is_selected_before_default() -> None:
    references = [
        ReferenceProject(
            project_code="pilot_001",
            project_label="Kilpikoivu",
            apartment_count=49,
            price_gross=Decimal("280000"),
            vertical_stack_count=15,
            includes_base_drain=True,
            includes_plot_line=True,
        ),
        ReferenceProject(
            project_code="close_ref",
            project_label="Close reference",
            apartment_count=30,
            price_gross=Decimal("210000"),
            vertical_stack_count=9,
            includes_base_drain=True,
            includes_plot_line=True,
        ),
    ]

    estimate = estimate_jv_price(
        apartment_count=31,
        vertical_stack_count=9,
        references=references,
    )

    assert estimate.reference_project_code == "close_ref"
    assert estimate.reference_similarity_score > Decimal("0.9000")
    assert estimate.compared_reference_count == 2
