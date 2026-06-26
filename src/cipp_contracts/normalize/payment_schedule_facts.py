from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg


PAYMENT_TERMS = [
    "maksuerä",
    "maksuerätaulukko",
    "maksuerät",
    "erä",
    "laskutuserä",
    "maksuposti",
    "urakkahinta",
    "yhteensä",
    "alv 0",
    "€",
    "%",
]

PAYMENT_DOCUMENT_TYPES = {
    "payment_schedule",
    "contractor_offer",
    "main_contract",
    "contract_terms",
    "appendix",
    "financial_final_report",
    "financial_tracking",
    "project_management_table",
    "handover_minutes",
    "payment_approval",
}

MONEY_PATTERN = re.compile(r"-?\d+(?:[ .]\d{3})*(?:[,.]\d+)?")
ITEM_TOKEN_PATTERN = re.compile(r"^\s*(?P<item>\d{1,2})(?:\.\s*)?(?:erä|era)\b", re.I)
INTEGER_TOKEN_PATTERN = re.compile(r"^\s*(?P<item>\d{1,2})\s*$")


@dataclass(frozen=True)
class PaymentScheduleSource:
    source_layer: str
    source_id: str | None
    contract_document_id: str | None
    document_type: str | None
    source_label: str
    text: str
    page_no: int | None = None


@dataclass(frozen=True)
class ParsedPaymentScheduleItem:
    item_no: int
    description: str
    amount_net: Decimal
    vat_amount: Decimal | None
    amount_gross: Decimal | None
    vat_rate: Decimal | None
    confidence: str
    source: PaymentScheduleSource | None = None


@dataclass(frozen=True)
class ParsedPaymentSchedule:
    status: str
    items: list[ParsedPaymentScheduleItem] = field(default_factory=list)
    source: PaymentScheduleSource | None = None
    reason: str = ""

    @property
    def total_gross(self) -> Decimal | None:
        if not self.items or any(item.amount_gross is None for item in self.items):
            return None
        return sum((item.amount_gross for item in self.items if item.amount_gross), Decimal("0"))

    @property
    def total_net(self) -> Decimal | None:
        if not self.items:
            return None
        return sum((item.amount_net for item in self.items), Decimal("0"))


def contains_payment_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in PAYMENT_TERMS)


def parse_payment_schedule_text(
    text: str,
    source: PaymentScheduleSource | None = None,
) -> ParsedPaymentSchedule:
    if not contains_payment_terms(text):
        return ParsedPaymentSchedule(status="not_found", source=source, reason="No payment terms found.")

    items = _parse_pipe_rows(text, source) or _parse_compact_rows(text, source)
    if not items:
        return ParsedPaymentSchedule(
            status="found_unstructured",
            source=source,
            reason="Payment schedule terms found, but no reliable amount rows were parsed.",
        )
    if len(items) < 2:
        return ParsedPaymentSchedule(
            status="found_unstructured",
            source=source,
            reason="Only one payment row was parsed; this is not enough to prove a full schedule.",
        )

    item_numbers = [item.item_no for item in items]
    if len(item_numbers) != len(set(item_numbers)):
        return ParsedPaymentSchedule(
            status="found_unstructured",
            source=source,
            reason="Payment rows were found but item numbers were duplicated.",
        )

    return ParsedPaymentSchedule(
        status="structured",
        items=items,
        source=source,
        reason=f"Parsed {len(items)} payment schedule rows from text.",
    )


def should_insert_discovered_schedule(existing_count: int, parsed: ParsedPaymentSchedule) -> bool:
    return existing_count == 0 and parsed.status == "structured" and len(parsed.items) >= 2


def ensure_payment_schedule_items(
    conn: psycopg.Connection[Any],
    project_code: str,
    contract_id: Any,
) -> ParsedPaymentSchedule:
    existing_count = int(
        _fetch_scalar(
            conn,
            "SELECT count(*) FROM finance.payment_schedule_items WHERE contract_id = %s",
            (contract_id,),
        )
        or 0
    )
    if existing_count >= 2:
        return ParsedPaymentSchedule(
            status="structured_existing",
            reason=f"{existing_count} structured payment schedule rows already exist.",
        )

    parsed = discover_payment_schedule(conn, project_code, contract_id)
    if existing_count == 1 and parsed.status != "structured":
        conn.execute("DELETE FROM finance.payment_schedule_items WHERE contract_id = %s", (contract_id,))
        return parsed
    if existing_count == 1 and parsed.status == "structured":
        conn.execute("DELETE FROM finance.payment_schedule_items WHERE contract_id = %s", (contract_id,))
        existing_count = 0
    if should_insert_discovered_schedule(existing_count, parsed):
        _insert_payment_schedule_items(conn, contract_id, parsed.items)
    return parsed


def discover_payment_schedule(
    conn: psycopg.Connection[Any],
    project_code: str,
    contract_id: Any,
) -> ParsedPaymentSchedule:
    unstructured: ParsedPaymentSchedule | None = None
    for source in discover_payment_schedule_sources(conn, project_code, contract_id):
        parsed = parse_payment_schedule_text(source.text, source)
        if parsed.status == "structured":
            return parsed
        if parsed.status == "found_unstructured" and unstructured is None:
            unstructured = parsed
    return unstructured or ParsedPaymentSchedule(
        status="not_found",
        reason="Payment schedule was not found in finance, contract documents, doc text, or raw pages.",
    )


def discover_payment_schedule_sources(
    conn: psycopg.Connection[Any],
    project_code: str,
    contract_id: Any,
) -> list[PaymentScheduleSource]:
    patterns = [f"%{term}%" for term in PAYMENT_TERMS]
    sources: list[PaymentScheduleSource] = []
    sources.extend(_doc_section_sources(conn, project_code, patterns))
    sources.extend(_doc_clause_sources(conn, project_code, patterns))
    sources.extend(_raw_page_sources(conn, project_code, patterns))
    return sorted(sources, key=_source_rank)


def _parse_pipe_rows(
    text: str,
    source: PaymentScheduleSource | None,
) -> list[ParsedPaymentScheduleItem]:
    if "|" not in text:
        return []
    pipe_text = re.sub(r"\s+(\d{1,2}\.\s*(?:erä|era)\b)", r" | \1", text, flags=re.I)
    cells = [_clean_cell(cell) for cell in pipe_text.split("|")]
    items: list[ParsedPaymentScheduleItem] = []
    index = 0
    while index < len(cells):
        item_no = _item_no_from_cell(cells[index])
        description_index = index
        if item_no is None and index > 0 and _looks_like_item_number(cells[index]):
            previous = cells[index - 1]
            if _looks_like_payment_description(previous):
                item_no = int(cells[index])
                description_index = index - 1
        if item_no is None:
            index += 1
            continue

        row_end = _next_pipe_row_index(cells, index + 1)
        row_cells = cells[index + 1 : row_end]
        amounts = _amounts_from_cells(row_cells)
        money = _infer_money_triplet(amounts)
        if money:
            net, vat, gross = money
            items.append(
                ParsedPaymentScheduleItem(
                    item_no=item_no,
                    description=_description_from_cell(cells[description_index], item_no),
                    amount_net=net,
                    vat_amount=vat,
                    amount_gross=gross,
                    vat_rate=_vat_rate(net, vat),
                    confidence="high",
                    source=source,
                )
            )
        index = max(row_end, index + 1)
    return items


def _parse_compact_rows(
    text: str,
    source: PaymentScheduleSource | None,
) -> list[ParsedPaymentScheduleItem]:
    normalized = _normalize_text(text)
    pattern = re.compile(
        r"(?P<item>\d{1,2})\.\s*(?:erä|era)\s*"
        r"(?P<net>-?\d[\d ]*(?:[,.]\d+)?)\s*€?\s*"
        r"(?P<gross>-?\d[\d ]*(?:[,.]\d+)?)\s*€",
        re.I,
    )
    items: list[ParsedPaymentScheduleItem] = []
    for match in pattern.finditer(normalized):
        net = _decimal(match.group("net"))
        gross = _decimal(match.group("gross"))
        if net is None or gross is None or gross <= net:
            continue
        vat = (gross - net).quantize(Decimal("0.01"))
        items.append(
            ParsedPaymentScheduleItem(
                item_no=int(match.group("item")),
                description=f"{match.group('item')}. erä",
                amount_net=net,
                vat_amount=vat,
                amount_gross=gross,
                vat_rate=_vat_rate(net, vat),
                confidence="medium_high",
                source=source,
            )
        )
    return items


def _insert_payment_schedule_items(
    conn: psycopg.Connection[Any],
    contract_id: Any,
    items: list[ParsedPaymentScheduleItem],
) -> None:
    for item in items:
        conn.execute(
            """
            INSERT INTO finance.payment_schedule_items (
                contract_id, item_no, amount_net, vat_rate, vat_amount,
                amount_gross, payment_condition, source_document_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (contract_id, item_no) DO UPDATE
            SET amount_net = EXCLUDED.amount_net,
                vat_rate = EXCLUDED.vat_rate,
                vat_amount = EXCLUDED.vat_amount,
                amount_gross = EXCLUDED.amount_gross,
                payment_condition = EXCLUDED.payment_condition,
                source_document_id = EXCLUDED.source_document_id
            """,
            (
                contract_id,
                item.item_no,
                item.amount_net,
                item.vat_rate,
                item.vat_amount,
                item.amount_gross,
                item.description,
                item.source.contract_document_id if item.source else None,
            ),
        )


def _doc_section_sources(
    conn: psycopg.Connection[Any],
    project_code: str,
    patterns: list[str],
) -> list[PaymentScheduleSource]:
    rows = conn.execute(
        """
        SELECT
            ds.id AS source_id,
            cd.id AS contract_document_id,
            cd.document_type,
            coalesce(ds.title, cd.document_title_redacted) AS source_label,
            ds.body_text AS text,
            ds.page_start AS page_no
        FROM doc.sections ds
        JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
        JOIN core.contracts c ON c.id = cd.contract_id
        JOIN core.projects p ON p.id = c.project_id
        WHERE p.project_code = %s
          AND ds.body_text ILIKE ANY(%s)
        """,
        (project_code, patterns),
    ).fetchall()
    return [
        PaymentScheduleSource(
            source_layer="doc.sections",
            source_id=str(row["source_id"]),
            contract_document_id=str(row["contract_document_id"]),
            document_type=row["document_type"],
            source_label=row["source_label"],
            text=row["text"],
            page_no=row["page_no"],
        )
        for row in rows
    ]


def _doc_clause_sources(
    conn: psycopg.Connection[Any],
    project_code: str,
    patterns: list[str],
) -> list[PaymentScheduleSource]:
    rows = conn.execute(
        """
        SELECT
            dc.id AS source_id,
            cd.id AS contract_document_id,
            cd.document_type,
            coalesce(dc.title, ds.title, cd.document_title_redacted) AS source_label,
            dc.clause_text AS text,
            dc.source_page AS page_no
        FROM doc.clauses dc
        JOIN doc.sections ds ON ds.id = dc.section_id
        JOIN core.contract_documents cd ON cd.id = ds.contract_document_id
        JOIN core.contracts c ON c.id = cd.contract_id
        JOIN core.projects p ON p.id = c.project_id
        WHERE p.project_code = %s
          AND dc.clause_text ILIKE ANY(%s)
        """,
        (project_code, patterns),
    ).fetchall()
    return [
        PaymentScheduleSource(
            source_layer="doc.clauses",
            source_id=str(row["source_id"]),
            contract_document_id=str(row["contract_document_id"]),
            document_type=row["document_type"],
            source_label=row["source_label"],
            text=row["text"],
            page_no=row["page_no"],
        )
        for row in rows
    ]


def _raw_page_sources(
    conn: psycopg.Connection[Any],
    project_code: str,
    patterns: list[str],
) -> list[PaymentScheduleSource]:
    rows = conn.execute(
        """
        SELECT
            rp.id AS source_id,
            cd.id AS contract_document_id,
            coalesce(cd.document_type, sf.document_type) AS document_type,
            sf.original_filename AS source_label,
            rp.raw_text AS text,
            rp.page_no
        FROM raw.pages rp
        JOIN raw.source_files sf ON sf.id = rp.source_file_id
        LEFT JOIN core.contract_documents cd ON cd.source_file_id = sf.id
        WHERE sf.project_code = %s
          AND rp.raw_text ILIKE ANY(%s)
        """,
        (project_code, patterns),
    ).fetchall()
    return [
        PaymentScheduleSource(
            source_layer="raw.pages",
            source_id=str(row["source_id"]),
            contract_document_id=str(row["contract_document_id"])
            if row["contract_document_id"]
            else None,
            document_type=row["document_type"],
            source_label=row["source_label"],
            text=row["text"] or "",
            page_no=row["page_no"],
        )
        for row in rows
    ]


def _source_rank(source: PaymentScheduleSource) -> tuple[int, int, str]:
    document_type = source.document_type or ""
    if document_type == "payment_schedule":
        doc_rank = 0
    elif document_type in {"financial_final_report", "financial_tracking", "project_management_table"}:
        doc_rank = 1
    elif document_type in PAYMENT_DOCUMENT_TYPES:
        doc_rank = 2
    else:
        doc_rank = 3
    layer_rank = {"doc.sections": 0, "doc.clauses": 1, "raw.pages": 2}.get(source.source_layer, 9)
    return doc_rank, layer_rank, source.source_label


def _next_pipe_row_index(cells: list[str], start: int) -> int:
    for index in range(start, len(cells)):
        if _item_no_from_cell(cells[index]) is not None:
            return index
        if (
            index + 1 < len(cells)
            and _looks_like_item_number(cells[index + 1])
            and _looks_like_payment_description(cells[index])
        ):
            return index + 1
        if (
            _looks_like_item_number(cells[index])
            and index > 0
            and _looks_like_payment_description(cells[index - 1])
        ):
            return index - 1
        lower = cells[index].lower()
        if lower.startswith(("yhteensä", "yhteensa", "lisä", "lisa", "hyvity")):
            return index
        if "yhteensä" in lower or "yhteensa" in lower:
            return index + 1
    return len(cells)


def _item_no_from_cell(cell: str) -> int | None:
    match = ITEM_TOKEN_PATTERN.match(cell)
    return int(match.group("item")) if match else None


def _looks_like_item_number(cell: str) -> bool:
    match = INTEGER_TOKEN_PATTERN.match(cell)
    return bool(match and 1 <= int(match.group("item")) <= 50)


def _looks_like_payment_description(cell: str) -> bool:
    lower = cell.lower()
    return any(
        token in lower
        for token in (
            "laskutetaan",
            "työ",
            "tyo",
            "pysty",
            "pohja",
            "vastaanotettu",
            "erä",
            "era",
        )
    )


def _amounts_from_cells(cells: list[str]) -> list[Decimal]:
    amounts: list[Decimal] = []
    for cell in cells:
        for raw in MONEY_PATTERN.findall(cell):
            value = _decimal(raw)
            if value is None:
                continue
            if _looks_like_excel_date_or_invoice(raw, value):
                continue
            amounts.append(value)
    return amounts


def _infer_money_triplet(amounts: list[Decimal]) -> tuple[Decimal, Decimal | None, Decimal | None] | None:
    if len(amounts) < 2:
        return None
    candidates = amounts[:4]
    for first in candidates:
        for second in candidates:
            for third in candidates:
                if len({first, second, third}) < 3:
                    continue
                values = sorted([first, second, third])
                vat, net, gross = values[0], values[1], values[2]
                if abs((net + vat) - gross) <= Decimal("1.00"):
                    return (
                        net.quantize(Decimal("0.01")),
                        vat.quantize(Decimal("0.01")),
                        gross.quantize(Decimal("0.01")),
                    )
    first, second = amounts[0], amounts[1]
    smaller, larger = sorted([first, second])
    if larger and Decimal("0.20") <= smaller / larger <= Decimal("0.28"):
        net, vat = larger, smaller
        gross = net + vat
        return net.quantize(Decimal("0.01")), vat.quantize(Decimal("0.01")), gross.quantize(Decimal("0.01"))
    if len(amounts) >= 2:
        net, gross = amounts[0], amounts[1]
        if gross > net and Decimal("1.20") <= gross / net <= Decimal("1.30"):
            vat = (gross - net).quantize(Decimal("0.01"))
            return net.quantize(Decimal("0.01")), vat, gross.quantize(Decimal("0.01"))
    return None


def _looks_like_excel_date_or_invoice(raw: str, value: Decimal) -> bool:
    compact = raw.strip()
    has_decimal = "," in compact or "." in compact
    if not has_decimal and Decimal("40000") <= value <= Decimal("50000"):
        return True
    if not has_decimal and value >= Decimal("100000"):
        return True
    return False


def _vat_rate(net: Decimal, vat: Decimal | None) -> Decimal | None:
    if vat is None or net == 0:
        return None
    return ((vat / net) * Decimal("100")).quantize(Decimal("0.01"))


def _description_from_cell(cell: str, item_no: int) -> str:
    description = re.sub(r"^\s*\d{1,2}(?:\.\s*)?(?:erä|era)\s*,?", "", cell, flags=re.I)
    description = description.strip(" ,-")
    return description or f"{item_no}. erä"


def _clean_cell(cell: str) -> str:
    return _normalize_text(cell).strip()


def _normalize_text(text: str) -> str:
    return (
        text.replace("\u00ad", "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\xa0", " ")
    )


def _decimal(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _fetch_scalar(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> Any:
    row = conn.execute(sql, params).fetchone()
    return next(iter(row.values())) if row else None
