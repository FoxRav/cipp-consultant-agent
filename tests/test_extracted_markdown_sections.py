from __future__ import annotations

from cipp_contracts.extract.build_markdown import render_document_markdown
from cipp_contracts.load.load_markdown_sections import parse_markdown_sections


def test_render_document_markdown_includes_extractor_metadata() -> None:
    source_id = "11111111-1111-1111-1111-111111111111"
    markdown, findings = render_document_markdown(
        "drawing",
        [{"id": source_id, "original_filename": "scan.pdf"}],
        {
            source_id: [
                {
                    "page_no": 1,
                    "raw_text": "OCR text from DWG derived PDF",
                    "extractor_name": "doclayout_ai_visual_ocr",
                    "extraction_status": "completed",
                }
            ]
        },
    )

    assert findings == []
    assert "# drawing" in markdown
    assert "## Source 001 / Page 001: scan.pdf" in markdown
    assert "Extractor: `doclayout_ai_visual_ocr`" in markdown
    assert "OCR text from DWG derived PDF" in markdown


def test_parse_source_page_markdown_sections() -> None:
    markdown = """# drawing

## Source 001 / Page 002: scan.pdf

Source file: `scan.pdf`
Extractor: `doclayout_ai_visual_ocr`

OCR text
"""

    sections = parse_markdown_sections(markdown)

    assert len(sections) == 1
    assert sections[0]["section_key"] == "source_001_page_002"
    assert sections[0]["page_no"] == 2
    assert sections[0]["clause_type"] == "extracted_page_text"
    assert sections[0]["metadata"]["source_filename"] == "scan.pdf"
    assert sections[0]["metadata"]["source_file"] == "scan.pdf"
    assert sections[0]["metadata"]["extractor_name"] == "doclayout_ai_visual_ocr"
    assert "OCR text" in sections[0]["body_text"]


def test_parse_legacy_page_markdown_sections() -> None:
    markdown = """# main_contract

## Page 1

Legacy PDF text
"""

    sections = parse_markdown_sections(markdown)

    assert len(sections) == 1
    assert sections[0]["section_key"] == "page_001"
    assert sections[0]["page_no"] == 1
    assert sections[0]["clause_type"] == "page_text"
