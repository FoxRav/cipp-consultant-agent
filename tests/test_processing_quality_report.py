from __future__ import annotations

from cipp_contracts.extract.report_processing_quality import evaluate_project_status


def base_row() -> dict[str, int]:
    return {
        "source_files_total": 3,
        "source_files_with_raw_pages": 3,
        "raw_pages_count": 9,
        "markdown_documents_count": 2,
        "doc_sections_count": 9,
        "source_files_without_text_or_status": 0,
        "latest_failed_extraction_runs": 0,
    }


def test_quality_status_ok_when_raw_pages_and_sections_exist() -> None:
    status, warnings = evaluate_project_status(base_row())

    assert status == "ok"
    assert warnings == []


def test_quality_status_fail_when_sections_missing() -> None:
    row = base_row()
    row["doc_sections_count"] = 0

    status, warnings = evaluate_project_status(row)

    assert status == "fail"
    assert "no doc.sections records" in warnings


def test_quality_status_fail_when_source_file_has_no_text_or_status() -> None:
    row = base_row()
    row["source_files_without_text_or_status"] = 1

    status, warnings = evaluate_project_status(row)

    assert status == "fail"
    assert "1 source files without text or latest status" in warnings


def test_quality_status_warning_for_latest_failures_only() -> None:
    row = base_row()
    row["latest_failed_extraction_runs"] = 2

    status, warnings = evaluate_project_status(row)

    assert status == "warning"
    assert "2 latest failed extraction runs" in warnings
