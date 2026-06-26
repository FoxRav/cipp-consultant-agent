from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


REQUIRED_DOCUMENT_TYPES = {
    "law_rakentamislaki_751_2023",
    "law_alueidenkayttolaki_132_1999",
    "main_contract",
    "yse_1998",
    "negotiation_minutes",
    "contract_terms",
    "rfq",
    "rfq_clarification",
    "contractor_offer",
    "unit_prices",
    "payment_schedule",
    "drawing_index",
    "quality_manual",
    "security_document",
}


REQUIRED_TOP_LEVEL_KEYS = {
    "project_code",
    "project_type",
    "property",
    "contract",
    "parties",
    "documents",
}


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    issue_type: str
    message: str
    path: str = "$"


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Not a decimal value: {value!r}") from exc
