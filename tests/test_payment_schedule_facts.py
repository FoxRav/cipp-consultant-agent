from __future__ import annotations

from decimal import Decimal

from cipp_contracts.normalize.payment_schedule_facts import (
    PaymentScheduleSource,
    ParsedPaymentSchedule,
    ParsedPaymentScheduleItem,
    discover_payment_schedule_sources,
    parse_payment_schedule_text,
    should_insert_discovered_schedule,
)


def source(document_type: str = "payment_schedule") -> PaymentScheduleSource:
    return PaymentScheduleSource(
        source_layer="doc.sections",
        source_id="section-1",
        contract_document_id="document-1",
        document_type=document_type,
        source_label="Fixture",
        text="",
    )


def test_parser_finds_pipe_table_from_payment_schedule_text() -> None:
    text = (
        "Maksuerätaulukko | Eränumero | Maksu € | Alv. | sis. 24% alv "
        "Työn aloitus | 1 | 5645.16 | 1354.84 | 7000 "
        "Pystylinja valmis | 2 | 7997.31 | 1919.35 | 9916.66 "
        "Yhteensä | 13642.47 | 3274.19 | 16916.66"
    )

    parsed = parse_payment_schedule_text(text, source())

    assert parsed.status == "structured"
    assert len(parsed.items) == 2
    assert parsed.items[0].item_no == 1
    assert parsed.items[0].amount_net == Decimal("5645.16")
    assert parsed.items[0].amount_gross == Decimal("7000.00")
    assert parsed.total_gross == Decimal("16916.66")


def test_parser_finds_schedule_from_other_document_type() -> None:
    text = (
        "Taloudellinen loppuselvitys | Laskunumero | ALV0% | ALV24% | Yhteensä "
        "1. erä | 2564 | 18188.89 | 4365.33 | 22554.22 | 42117 "
        "2. erä | 2565 | 18188.89 | 4365.33 | 22554.22 | 42117"
    )

    parsed = parse_payment_schedule_text(text, source("financial_final_report"))

    assert parsed.status == "structured"
    assert [item.item_no for item in parsed.items] == [1, 2]
    assert parsed.total_gross == Decimal("45108.44")


def test_parser_finds_compact_rows_and_calculates_total() -> None:
    text = (
        "MAKSUERÄTAULUKKO "
        "1. erä20 000,00 €24 800,00 €"
        "2. erä20 806,00 €25 799,44 €"
        "Yhteensä40 806,00 €50 599,44 €"
    )

    parsed = parse_payment_schedule_text(text, source())

    assert parsed.status == "structured"
    assert len(parsed.items) == 2
    assert parsed.items[1].vat_amount == Decimal("4993.44")
    assert parsed.total_gross == Decimal("50599.44")


def test_parser_does_not_guess_missing_amounts() -> None:
    text = "Maksuerätaulukko | 1. erä , kun työ alkaa | summa myöhemmin"

    parsed = parse_payment_schedule_text(text, source())

    assert parsed.status == "found_unstructured"
    assert parsed.items == []


def test_found_unstructured_is_not_insertable() -> None:
    parsed = ParsedPaymentSchedule(status="found_unstructured")

    assert should_insert_discovered_schedule(0, parsed) is False


def test_structured_schedule_is_insertable_only_once() -> None:
    parsed = ParsedPaymentSchedule(
        status="structured",
        items=[
            ParsedPaymentScheduleItem(
                item_no=1,
                description="1. erä",
                amount_net=Decimal("100.00"),
                vat_amount=Decimal("24.00"),
                amount_gross=Decimal("124.00"),
                vat_rate=Decimal("24.00"),
                confidence="high",
            ),
            ParsedPaymentScheduleItem(
                item_no=2,
                description="2. erä",
                amount_net=Decimal("100.00"),
                vat_amount=Decimal("24.00"),
                amount_gross=Decimal("124.00"),
                vat_rate=Decimal("24.00"),
                confidence="high",
            ),
        ],
    )

    assert should_insert_discovered_schedule(0, parsed) is True
    assert should_insert_discovered_schedule(1, parsed) is False


def test_discovery_query_includes_multiple_text_layers() -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.sql: list[str] = []

        def execute(self, sql: str, params: object) -> "FakeResult":
            self.sql.append(sql)
            return FakeResult()

    class FakeResult:
        def fetchall(self) -> list[dict[str, object]]:
            return []

    conn = FakeConnection()

    discover_payment_schedule_sources(conn, "reference", "contract")

    joined = "\n".join(conn.sql)
    assert "doc.sections" in joined
    assert "doc.clauses" in joined
    assert "raw.pages" in joined
