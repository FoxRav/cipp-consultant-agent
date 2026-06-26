from __future__ import annotations

from cipp_contracts.legal.import_guidance_pdf import (
    AUTHORITY_LEVEL,
    BINDING_STATUS,
    SOURCE_TYPE,
    GuidanceSection,
    ParsedPage,
    extract_guidance_items,
    identify_sections,
)


def fixture_pages() -> list[ParsedPage]:
    return [
        ParsedPage(
            1,
            "Johdanto. Taloyhtiön hallituksen kannattaa aloittaa hankesuunnittelu ajoissa. "
            "Osakkaille on syytä tiedottaa vaihtoehdoista.",
        ),
        ParsedPage(
            2,
            "Korjausvaihtoehdot. Sukitus soveltuu viemäriputkistoon vain, jos kuntotutkimus tukee menetelmän valintaa. "
            "Pinnoitukseen liittyy riski, jos putken kuntoa ei ole arvioitu.",
        ),
    ]


def test_guidance_document_classification_constants() -> None:
    assert SOURCE_TYPE == "expert_guidance"
    assert AUTHORITY_LEVEL == "non_binding_guidance"
    assert BINDING_STATUS == "not_binding_law"


def test_sections_are_identified_from_fixture_pages() -> None:
    sections = identify_sections(fixture_pages())

    assert sections
    assert any(section.title == "Johdanto" for section in sections)


def test_guidance_items_are_extracted_with_page_reference() -> None:
    sections = identify_sections(fixture_pages())
    items = extract_guidance_items(fixture_pages(), sections)

    assert items
    assert all(item.page_number for item in items)
    assert all(item.binding_status == "not_binding_law" for item in items)


def test_import_tests_use_short_fictional_fixture_text() -> None:
    text_length = sum(len(page.text) for page in fixture_pages())

    assert text_length < 600


def test_section_dataclass_supports_page_range() -> None:
    section = GuidanceSection("1", "Johdanto", 1, 2, "hash")

    assert section.page_start == 1
    assert section.page_end == 2
