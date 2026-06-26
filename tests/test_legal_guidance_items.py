from __future__ import annotations

from cipp_contracts.legal.import_guidance_pdf import (
    GuidanceSection,
    ParsedPage,
    classify_item_type,
    detect_legal_references,
    extract_guidance_items,
)


def test_kannattaa_does_not_become_binding_obligation() -> None:
    pages = [ParsedPage(1, "Hallituksen kannattaa selvittää korjausvaihtoehdot ennen päätöstä.")]
    sections = [GuidanceSection("1", "Johdanto", 1, 1, "hash")]

    item = extract_guidance_items(pages, sections)[0]

    assert item.binding_status == "not_binding_law"
    assert item.legal_relevance == "Non-binding expert guidance for planning, decisions, or checks."


def test_edellyttaa_is_stronger_only_with_norm_reference() -> None:
    weak_type = classify_item_type("hanke edellyttää hyvää suunnittelua", [])
    legal_type = classify_item_type(
        "hanke edellyttää turvallisuuskoordinaattoria rakennustyön turvallisuusasetus 205/2009 mukaan",
        ["rakennustyon_turvallisuusasetus_205_2009"],
    )

    assert weak_type != "legal_cross_reference"
    assert legal_type == "legal_cross_reference"


def test_legal_reference_is_mentioned_not_verified_metadata() -> None:
    pages = [
        ParsedPage(
            1,
            "Rakennustyön turvallisuusasetus 205/2009 edellyttää turvallisuuskoordinaattorin nimeämistä.",
        )
    ]
    sections = [GuidanceSection("5", "Taloyhtiön korjaushanke pähkinänkuoressa", 1, 1, "hash")]

    item = extract_guidance_items(pages, sections)[0]

    assert item.item_type == "legal_cross_reference"
    assert item.metadata["legal_references"] == ["rakennustyon_turvallisuusasetus_205_2009"]
    assert "mentioned_not_verified" in item.legal_relevance


def test_detect_legal_references_by_number() -> None:
    refs = detect_legal_references("asetuksessa 782/2017 puhutaan kosteusteknisestä toimivuudesta")

    assert "kosteustekninen_toimivuus_782_2017" in refs
