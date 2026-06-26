from __future__ import annotations

import argparse
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from cipp_contracts.jsonio import read_json
from cipp_contracts.model import (
    REQUIRED_DOCUMENT_TYPES,
    REQUIRED_TOP_LEVEL_KEYS,
    ValidationIssue,
    decimal_or_none,
)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+358|0)\s?(?:\d[\s-]?){6,12}(?!\d)")


def validate(data: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for key in sorted(REQUIRED_TOP_LEVEL_KEYS - data.keys()):
        issues.append(ValidationIssue("error", "missing_key", f"Missing top-level key: {key}", f"$.{key}"))

    _validate_documents(data, issues)
    _validate_parties(data, issues)
    _validate_money(data, issues)
    _validate_pii(data, issues)
    return issues


def _validate_documents(data: dict[str, Any], issues: list[ValidationIssue]) -> None:
    documents = data.get("documents") or []
    if not isinstance(documents, list):
        issues.append(ValidationIssue("error", "invalid_type", "documents must be a list", "$.documents"))
        return

    seen = {doc.get("document_type") for doc in documents if isinstance(doc, dict)}
    missing = REQUIRED_DOCUMENT_TYPES - seen
    for document_type in sorted(missing):
        issues.append(
            ValidationIssue(
                "warning",
                "missing_document_type",
                f"Expected document type is missing: {document_type}",
                "$.documents",
            )
        )

    ranks = [
        doc.get("precedence_rank")
        for doc in documents
        if isinstance(doc, dict)
        and doc.get("precedence_rank") is not None
        and doc.get("precedence_rank") != 0
    ]
    if len(ranks) != len(set(ranks)):
        issues.append(
            ValidationIssue(
                "error",
                "duplicate_precedence_rank",
                "Document precedence_rank values must be unique when present",
                "$.documents",
            )
        )


def _validate_parties(data: dict[str, Any], issues: list[ValidationIssue]) -> None:
    parties = data.get("parties") or []
    if not isinstance(parties, list):
        issues.append(ValidationIssue("error", "invalid_type", "parties must be a list", "$.parties"))
        return
    for index, party in enumerate(parties):
        if not isinstance(party, dict):
            issues.append(ValidationIssue("error", "invalid_type", "party must be an object", f"$.parties[{index}]"))
            continue
        for key in ("party_code", "party_type", "role", "display_name_redacted"):
            if not party.get(key):
                issues.append(
                    ValidationIssue("error", "missing_party_field", f"Party missing {key}", f"$.parties[{index}].{key}")
                )


def _validate_money(data: dict[str, Any], issues: list[ValidationIssue]) -> None:
    for index, price in enumerate(data.get("prices") or []):
        if not isinstance(price, dict):
            continue
        net = decimal_or_none(price.get("amount_net"))
        vat = decimal_or_none(price.get("vat_amount"))
        gross = decimal_or_none(price.get("amount_gross"))
        vat_rate = decimal_or_none(price.get("vat_rate"))
        path = f"$.prices[{index}]"
        _check_vat_math(net, vat, gross, vat_rate, path, issues)

    schedule_total = Decimal("0")
    has_schedule = False
    for index, item in enumerate(data.get("payment_schedule") or []):
        if not isinstance(item, dict):
            continue
        has_schedule = True
        net = decimal_or_none(item.get("amount_net"))
        vat = decimal_or_none(item.get("vat_amount"))
        gross = decimal_or_none(item.get("amount_gross"))
        vat_rate = decimal_or_none(item.get("vat_rate"))
        if net is not None:
            schedule_total += net
        _check_vat_math(net, vat, gross, vat_rate, f"$.payment_schedule[{index}]", issues)

    contract_total = None
    for price in data.get("prices") or []:
        if isinstance(price, dict) and price.get("price_type") == "fixed_contract_price":
            contract_total = decimal_or_none(price.get("amount_net"))
            break
    if has_schedule and contract_total is not None and schedule_total != contract_total:
        severity = "warning" if abs(schedule_total - contract_total) <= Decimal("0.05") else "error"
        issues.append(
            ValidationIssue(
                severity,
                "payment_schedule_total_mismatch",
                f"Payment schedule net total {schedule_total} does not equal contract net price {contract_total}",
                "$.payment_schedule",
            )
        )


def _check_vat_math(
    net: Decimal | None,
    vat: Decimal | None,
    gross: Decimal | None,
    vat_rate: Decimal | None,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    cent = Decimal("0.01")
    if net is not None and vat is not None and gross is not None and (net + vat).quantize(cent) != gross.quantize(cent):
        delta = abs((net + vat) - gross)
        severity = "warning" if delta <= Decimal("0.05") else "error"
        issues.append(ValidationIssue(severity, "vat_sum_mismatch", "amount_net + vat_amount must equal amount_gross", path))
    if net is not None and vat is not None and vat_rate is not None:
        expected = (net * vat_rate / Decimal("100")).quantize(cent)
        if expected != vat.quantize(cent):
            severity = "warning" if abs(expected - vat) <= Decimal("0.05") else "error"
            issues.append(ValidationIssue(severity, "vat_rate_mismatch", f"VAT should be {expected}, got {vat}", path))


def _validate_pii(data: dict[str, Any], issues: list[ValidationIssue]) -> None:
    text = repr(data)
    if EMAIL_RE.search(text):
        issues.append(ValidationIssue("critical", "pii_email", "Canonical JSON appears to contain an email address"))
    if PHONE_RE.search(text):
        issues.append(ValidationIssue("warning", "pii_phone", "Canonical JSON may contain a phone number"))


def write_report(path: Path, issues: list[ValidationIssue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "valid" if not any(issue.severity in {"error", "critical"} for issue in issues) else "invalid"
    lines = ["# Canonical Contract Validation", "", f"Status: `{status}`", "", "## Issues", ""]
    if not issues:
        lines.append("No issues found.")
    else:
        for issue in issues:
            lines.append(f"- `{issue.severity}` `{issue.issue_type}` at `{issue.path}`: {issue.message}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    issues = validate(read_json(args.input))
    write_report(args.report, issues)
    print(f"Wrote validation report to {args.report}")
    if any(issue.severity in {"error", "critical"} for issue in issues):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
