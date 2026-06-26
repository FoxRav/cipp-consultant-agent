from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cipp_contracts.config import database_url


RULE_CODE = "jv_all_lines_apartment_weighted_v1"
REFERENCE_PROJECT_CODE = "pilot_001"
REFERENCE_PROJECT_LABEL = "As Oy Kilpikoivu"
REFERENCE_APARTMENTS = Decimal("49")
REFERENCE_VERTICAL_STACKS = Decimal("15")
REFERENCE_PRICE_GROSS = Decimal("280000")

MIN_PRICE_PER_APARTMENT = Decimal("5000")
MAX_PRICE_PER_APARTMENT = Decimal("8000")
KILPIKOIVU_PRICE_PER_APARTMENT = REFERENCE_PRICE_GROSS / REFERENCE_APARTMENTS

APARTMENT_WEIGHT = Decimal("0.70")
VERTICAL_STACK_WEIGHT = Decimal("0.10")
BASE_DRAIN_WEIGHT = Decimal("0.10")
PLOT_LINE_WEIGHT = Decimal("0.10")


@dataclass(frozen=True)
class ReferenceProject:
    project_code: str
    project_label: str
    apartment_count: int
    price_gross: Decimal
    vertical_stack_count: int | None
    includes_base_drain: bool
    includes_plot_line: bool


@dataclass(frozen=True)
class ReferenceMatch:
    project_code: str
    project_label: str
    similarity_score: Decimal
    apartment_count: int
    price_gross: Decimal
    price_per_apartment_gross: Decimal
    vertical_stack_count: int | None
    includes_base_drain: bool
    includes_plot_line: bool


@dataclass(frozen=True)
class JvPriceEstimate:
    rule_code: str
    apartment_count: int
    estimated_price_gross: Decimal
    low_price_gross: Decimal
    high_price_gross: Decimal
    estimated_price_per_apartment_gross: Decimal
    low_price_per_apartment_gross: Decimal
    high_price_per_apartment_gross: Decimal
    weighted_multiplier: Decimal
    reference_project_code: str
    reference_project_label: str
    reference_similarity_score: Decimal
    compared_reference_count: int
    assumptions: dict[str, Any]


def estimate_jv_price(
    apartment_count: int,
    vertical_stack_count: int | None = None,
    base_drain_factor: Decimal | int | float | str = Decimal("1"),
    plot_line_factor: Decimal | int | float | str = Decimal("1"),
    references: list[ReferenceProject] | None = None,
) -> JvPriceEstimate:
    if apartment_count <= 0:
        raise ValueError("apartment_count must be positive")
    if vertical_stack_count is not None and vertical_stack_count <= 0:
        raise ValueError("vertical_stack_count must be positive when provided")

    apartments = Decimal(apartment_count)
    base_factor = Decimal(str(base_drain_factor))
    plot_factor = Decimal(str(plot_line_factor))
    vertical_factor = _vertical_stack_factor(apartments, vertical_stack_count)
    reference = select_reference_project(
        references or [kilpikoivu_reference()],
        apartment_count=apartment_count,
        vertical_stack_count=vertical_stack_count,
        includes_base_drain=base_factor > 0,
        includes_plot_line=plot_factor > 0,
    )

    price_per_apartment = _reference_adjusted_price_per_apartment(apartments, reference)
    scope_multiplier = (
        APARTMENT_WEIGHT
        + (VERTICAL_STACK_WEIGHT * vertical_factor)
        + (BASE_DRAIN_WEIGHT * base_factor)
        + (PLOT_LINE_WEIGHT * plot_factor)
    )
    estimate = apartments * price_per_apartment * scope_multiplier

    return JvPriceEstimate(
        rule_code=RULE_CODE,
        apartment_count=apartment_count,
        estimated_price_gross=_money(estimate),
        low_price_gross=_money(apartments * MIN_PRICE_PER_APARTMENT * scope_multiplier),
        high_price_gross=_money(apartments * MAX_PRICE_PER_APARTMENT * scope_multiplier),
        estimated_price_per_apartment_gross=_money(estimate / apartments),
        low_price_per_apartment_gross=MIN_PRICE_PER_APARTMENT,
        high_price_per_apartment_gross=MAX_PRICE_PER_APARTMENT,
        weighted_multiplier=_quant(scope_multiplier, Decimal("0.0001")),
        reference_project_code=reference.project_code,
        reference_project_label=reference.project_label,
        reference_similarity_score=reference.similarity_score,
        compared_reference_count=len(references or [kilpikoivu_reference()]),
        assumptions={
            "currency": "EUR",
            "vat": "gross customer-facing estimate",
            "material_quality": "best materials",
            "method": "liner-overlap CIPP",
            "apartment_count_weight": float(APARTMENT_WEIGHT),
            "vertical_stack_weight": float(VERTICAL_STACK_WEIGHT),
            "base_drain_weight": float(BASE_DRAIN_WEIGHT),
            "plot_line_weight": float(PLOT_LINE_WEIGHT),
            "vertical_stack_count": vertical_stack_count,
            "vertical_stack_factor": float(_quant(vertical_factor, Decimal("0.0001"))),
            "base_drain_factor": float(base_factor),
            "plot_line_factor": float(plot_factor),
            "reference_apartment_count": reference.apartment_count,
            "reference_vertical_stack_count": reference.vertical_stack_count,
            "reference_price_gross": float(reference.price_gross),
            "reference_price_per_apartment_gross": float(reference.price_per_apartment_gross),
            "reference_includes_base_drain": reference.includes_base_drain,
            "reference_includes_plot_line": reference.includes_plot_line,
            "reference_selection": "closest_available_internal_project",
        },
    )


def kilpikoivu_reference() -> ReferenceProject:
    return ReferenceProject(
        project_code=REFERENCE_PROJECT_CODE,
        project_label=REFERENCE_PROJECT_LABEL,
        apartment_count=int(REFERENCE_APARTMENTS),
        price_gross=REFERENCE_PRICE_GROSS,
        vertical_stack_count=int(REFERENCE_VERTICAL_STACKS),
        includes_base_drain=True,
        includes_plot_line=True,
    )


def select_reference_project(
    references: list[ReferenceProject],
    apartment_count: int,
    vertical_stack_count: int | None = None,
    includes_base_drain: bool = True,
    includes_plot_line: bool = True,
) -> ReferenceMatch:
    candidates = references or [kilpikoivu_reference()]
    matches = [
        _score_reference(
            reference,
            apartment_count=apartment_count,
            vertical_stack_count=vertical_stack_count,
            includes_base_drain=includes_base_drain,
            includes_plot_line=includes_plot_line,
        )
        for reference in candidates
    ]
    return max(matches, key=lambda match: (match.similarity_score, match.apartment_count))


def fetch_reference_projects(db_url: str) -> list[ReferenceProject]:
    with psycopg.connect(db_url, row_factory=dict_row, connect_timeout=5) as conn:
        rows = conn.execute(
            """
            SELECT p.project_code,
                   coalesce(
                       pr.metadata->>'project_label',
                       p.project_name_redacted,
                       p.project_code
                   ) AS project_label,
                   pr.apartment_count,
                   cp.amount_gross AS price_gross,
                   string_agg(si.item_name, ' ') AS scope_text,
                   bool_or(
                       ss.system_type = 'JV'
                       AND ss.segment_type = 'base_drain'
                       AND ss.included_in_contract IS true
                   ) AS includes_base_drain,
                   bool_or(
                       ss.system_type = 'JV'
                       AND ss.segment_type = 'plot_line'
                       AND ss.included_in_contract IS true
                   ) AS includes_plot_line
            FROM core.projects p
            JOIN core.contracts c ON c.project_id = p.id
            LEFT JOIN core.properties pr ON pr.project_id = p.id
            LEFT JOIN finance.contract_prices cp
                ON cp.contract_id = c.id
               AND cp.price_type = 'fixed_contract_price'
            LEFT JOIN domain.scope_items si ON si.contract_id = c.id
            LEFT JOIN domain.sewer_segments ss ON ss.contract_id = c.id
            GROUP BY
                p.project_code,
                p.project_name_redacted,
                pr.metadata,
                pr.apartment_count,
                cp.amount_gross
            ORDER BY p.project_code
            """
        ).fetchall()

    references = []
    for row in rows:
        if row["apartment_count"] is None or row["price_gross"] is None:
            continue
        references.append(
            ReferenceProject(
                project_code=row["project_code"],
                project_label=row["project_label"],
                apartment_count=row["apartment_count"],
                price_gross=row["price_gross"],
                vertical_stack_count=_parse_vertical_stack_count(row["scope_text"] or ""),
                includes_base_drain=bool(row["includes_base_drain"]),
                includes_plot_line=bool(row["includes_plot_line"]),
            )
        )
    return references or [kilpikoivu_reference()]


def ensure_price_estimate_table(db_url: str) -> None:
    with psycopg.connect(db_url, connect_timeout=5) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance.price_estimates (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                rule_code text NOT NULL,
                customer_label text,
                input_json jsonb NOT NULL,
                estimate_json jsonb NOT NULL,
                reference_project_code text REFERENCES core.projects(project_code),
                reference_similarity_score numeric(6,4),
                estimated_price_gross numeric(12,2) NOT NULL,
                low_price_gross numeric(12,2) NOT NULL,
                high_price_gross numeric(12,2) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            );
            """
        )
        conn.commit()


def save_price_estimate(
    db_url: str,
    estimate: JvPriceEstimate,
    input_payload: dict[str, Any],
    customer_label: str | None = None,
) -> str:
    ensure_price_estimate_table(db_url)
    estimate_payload = asdict(estimate)
    with psycopg.connect(db_url, connect_timeout=5) as conn:
        estimate_id = conn.execute(
            """
            INSERT INTO finance.price_estimates (
                rule_code,
                customer_label,
                input_json,
                estimate_json,
                reference_project_code,
                reference_similarity_score,
                estimated_price_gross,
                low_price_gross,
                high_price_gross
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                estimate.rule_code,
                customer_label,
                Jsonb(input_payload, dumps=_json_dumps),
                Jsonb(estimate_payload, dumps=_json_dumps),
                estimate.reference_project_code,
                estimate.reference_similarity_score,
                estimate.estimated_price_gross,
                estimate.low_price_gross,
                estimate.high_price_gross,
            ),
        ).fetchone()[0]
        conn.commit()
    return str(estimate_id)


def _score_reference(
    reference: ReferenceProject,
    apartment_count: int,
    vertical_stack_count: int | None,
    includes_base_drain: bool,
    includes_plot_line: bool,
) -> ReferenceMatch:
    apartment_similarity = _ratio_similarity(
        Decimal(apartment_count),
        Decimal(reference.apartment_count),
    )
    if vertical_stack_count is None or reference.vertical_stack_count is None:
        vertical_similarity = Decimal("0.50")
    else:
        vertical_similarity = _ratio_similarity(
            Decimal(vertical_stack_count),
            Decimal(reference.vertical_stack_count),
        )
    base_similarity = Decimal("1") if includes_base_drain == reference.includes_base_drain else Decimal("0")
    plot_similarity = Decimal("1") if includes_plot_line == reference.includes_plot_line else Decimal("0")
    score = (
        APARTMENT_WEIGHT * apartment_similarity
        + VERTICAL_STACK_WEIGHT * vertical_similarity
        + BASE_DRAIN_WEIGHT * base_similarity
        + PLOT_LINE_WEIGHT * plot_similarity
    )
    return ReferenceMatch(
        project_code=reference.project_code,
        project_label=reference.project_label,
        similarity_score=_quant(score, Decimal("0.0001")),
        apartment_count=reference.apartment_count,
        price_gross=reference.price_gross,
        price_per_apartment_gross=_money(reference.price_gross / Decimal(reference.apartment_count)),
        vertical_stack_count=reference.vertical_stack_count,
        includes_base_drain=reference.includes_base_drain,
        includes_plot_line=reference.includes_plot_line,
    )


def _reference_adjusted_price_per_apartment(
    apartments: Decimal,
    reference: ReferenceMatch,
) -> Decimal:
    reference_apartments = Decimal(reference.apartment_count)
    size_adjustment = _price_per_apartment(apartments) / _price_per_apartment(reference_apartments)
    adjusted = (reference.price_gross / reference_apartments) * size_adjustment
    return min(MAX_PRICE_PER_APARTMENT, max(MIN_PRICE_PER_APARTMENT, adjusted))


def _ratio_similarity(left: Decimal, right: Decimal) -> Decimal:
    if left <= 0 or right <= 0:
        return Decimal("0")
    return min(left, right) / max(left, right)


def _parse_vertical_stack_count(text: str) -> int | None:
    import re

    match = re.search(r"(\d+)\s+JV-pystylinjaa", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _vertical_stack_factor(
    apartments: Decimal,
    vertical_stack_count: int | None,
) -> Decimal:
    if vertical_stack_count is None:
        return Decimal("1")
    expected_stacks = REFERENCE_VERTICAL_STACKS * apartments / REFERENCE_APARTMENTS
    return Decimal(vertical_stack_count) / expected_stacks


def _price_per_apartment(apartments: Decimal) -> Decimal:
    if apartments <= 10:
        return MAX_PRICE_PER_APARTMENT
    if apartments < REFERENCE_APARTMENTS:
        return _linear_interpolate(
            apartments,
            Decimal("10"),
            REFERENCE_APARTMENTS,
            MAX_PRICE_PER_APARTMENT,
            KILPIKOIVU_PRICE_PER_APARTMENT,
        )
    if apartments < 100:
        return _linear_interpolate(
            apartments,
            REFERENCE_APARTMENTS,
            Decimal("100"),
            KILPIKOIVU_PRICE_PER_APARTMENT,
            MIN_PRICE_PER_APARTMENT,
        )
    return MIN_PRICE_PER_APARTMENT


def _linear_interpolate(
    x_value: Decimal,
    x_min: Decimal,
    x_max: Decimal,
    y_min: Decimal,
    y_max: Decimal,
) -> Decimal:
    return y_min + ((x_value - x_min) / (x_max - x_min)) * (y_max - y_min)


def _money(value: Decimal) -> Decimal:
    return _quant(value, Decimal("0.01"))


def _quant(value: Decimal, exp: Decimal) -> Decimal:
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apartments", required=True, type=int)
    parser.add_argument("--vertical-stacks", type=int)
    parser.add_argument("--base-drain-factor", default="1")
    parser.add_argument("--plot-line-factor", default="1")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--customer-label")
    args = parser.parse_args()

    db_url = database_url(args.db, args.env) if args.db or args.env.exists() else None
    references = fetch_reference_projects(db_url) if db_url else [kilpikoivu_reference()]
    estimate = estimate_jv_price(
        apartment_count=args.apartments,
        vertical_stack_count=args.vertical_stacks,
        base_drain_factor=args.base_drain_factor,
        plot_line_factor=args.plot_line_factor,
        references=references,
    )
    payload = {
        "apartment_count": args.apartments,
        "vertical_stack_count": args.vertical_stacks,
        "base_drain_factor": args.base_drain_factor,
        "plot_line_factor": args.plot_line_factor,
    }
    output = asdict(estimate)
    if args.save:
        if not db_url:
            raise ValueError("--save requires --db or .env with DATABASE_URL")
        output["saved_estimate_id"] = save_price_estimate(
            db_url,
            estimate,
            payload,
            customer_label=args.customer_label,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
