from __future__ import annotations

from decimal import Decimal

from cipp_contracts.normalize.payment_schedule_facts import (
    PaymentScheduleSource,
    ParsedPaymentSchedule,
    ParsedPaymentScheduleItem,
    discover_payment_schedule_sources,
    looks_like_payment_path,
    parse_invoice_document_schedule,
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


def invoice_source(item_no: int, text: str) -> PaymentScheduleSource:
    return PaymentScheduleSource(
        source_layer="raw.pages",
        source_id=f"page-{item_no}",
        contract_document_id=f"document-{item_no}",
        document_type="payment_approval",
        source_label=f"Example - Maksuerä Nro{item_no} hyväksyntä.pdf",
        text=text,
        source_path=f"data/raw/reference/Maksuerät ja hyväksyntä/maksuera-{item_no}.pdf",
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


def test_parser_ignores_dates_inside_payment_rows() -> None:
    text = (
        "MAKSUERÄT Maksuerä | hyväksytty | eräpäivä | € (sis.ALV24%) | € (sis ALV0%) "
        "| € (ALV24% osuus) "
        "1. erä ensimmäinen vaihe | x(MV10.12.2014) | 19.12.2014 | 18000 | 14516.13 | 3483.87 "
        "2. erä toinen vaihe | x(MV26.12.2014) | 2.1.2015 | 18000 | 14516.13 | 3483.87 "
        "3. erä luovutus | 6987.08 | 5634.74 | 1352.34 "
    )

    parsed = parse_payment_schedule_text(text, source("project_management_table"))

    assert parsed.status == "structured"
    assert [item.item_no for item in parsed.items] == [1, 2, 3]
    assert parsed.total_gross == Decimal("42987.08")


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


def test_payment_path_name_is_detected() -> None:
    assert looks_like_payment_path("source_package/Maksuerät ja hyväksyntä/lasku-1.pdf")
    assert looks_like_payment_path("source_package/maksuerat-ja-hyvaksyn/lasku-1.pdf")


def test_invoice_documents_form_payment_schedule() -> None:
    parsed = parse_invoice_document_schedule(
        [
            invoice_source(
                1,
                "LASKU 1001 Maksuerä 1: työ aloitettu "
                "Veroton yhteensä: 14516.13 ALV yhteensä: 3483.87 Yhteensä: 18000.00",
            ),
            invoice_source(
                2,
                "LASKU 1002 Maksuerä 2: työ valmis "
                "Veroton yhteensä: 14516.13 ALV yhteensä: 3483.87 Yhteensä: 18000.00",
            ),
            invoice_source(
                3,
                "LASKU 1003 Maksuerä 3: loppuasiakirjat toimitettu "
                "Veroton yhteensä: 5634.74 ALV yhteensä: 1352.34 Yhteensä: 6987.08",
            ),
        ]
    )

    assert parsed.status == "invoice_documents_structured"
    assert [item.item_no for item in parsed.items] == [1, 2, 3]
    assert parsed.total_gross == Decimal("42987.08")


def test_invoice_documents_missing_amounts_stay_unstructured() -> None:
    parsed = parse_invoice_document_schedule(
        [
            invoice_source(1, "Maksuerä 1 hyväksytty, summa myöhemmin"),
            invoice_source(2, "Maksuerä 2 hyväksytty, summa myöhemmin"),
        ]
    )

    assert parsed.status == "invoice_documents_found_unstructured"
    assert parsed.items == []


def test_found_unstructured_is_not_insertable() -> None:
    parsed = ParsedPaymentSchedule(status="found_unstructured")

    assert should_insert_discovered_schedule(0, parsed) is False


def test_invoice_structured_schedule_is_insertable() -> None:
    parsed = ParsedPaymentSchedule(
        status="invoice_documents_structured",
        items=[
            ParsedPaymentScheduleItem(
                item_no=1,
                description="invoice 1",
                amount_net=Decimal("100.00"),
                vat_amount=Decimal("24.00"),
                amount_gross=Decimal("124.00"),
                vat_rate=Decimal("24.00"),
                confidence="medium_high",
            ),
            ParsedPaymentScheduleItem(
                item_no=2,
                description="invoice 2",
                amount_net=Decimal("100.00"),
                vat_amount=Decimal("24.00"),
                amount_gross=Decimal("124.00"),
                vat_rate=Decimal("24.00"),
                confidence="medium_high",
            ),
        ],
    )

    assert should_insert_discovered_schedule(0, parsed) is True
    assert should_insert_discovered_schedule(2, parsed) is False


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
    assert "stored_path" in joined
