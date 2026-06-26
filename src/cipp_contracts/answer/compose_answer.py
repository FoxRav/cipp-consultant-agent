from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cipp_contracts.config import database_url
from cipp_contracts.retrieve.build_retrieval_packet import (
    PostgresRetrievalRepository,
    RetrievalLimits,
    build_retrieval_packet,
    build_user_case,
    parse_bool,
    sanitize_text,
)


GENERATION_MODE = "deterministic_source_grounded"
LLM_USED = False
SOURCE_PRIORITY = {
    "direct_clause": 0,
    "direct_section": 1,
    "direct_page": 2,
    "source_file_page": 3,
    "entity_source_fallback": 4,
    "topic_text_fallback": 5,
}
ANSWER_STATUSES = {"answered", "partial", "insufficient_evidence"}


@dataclass(frozen=True)
class TopicTemplate:
    key_points: tuple[str, ...]
    recommended_questions: tuple[str, ...]


TOPIC_TEMPLATES: dict[str, TopicTemplate] = {
    "payment": TopicTemplate(
        key_points=(
            "Maksuerät kannattaa käsitellä vaiheittain ja sitoa dokumentoituun hyväksyntään, jos lähteet tukevat tätä.",
            "Maksuerien perusteet ja hyväksyntäketju kannattaa kirjata niin, että ne voidaan todentaa myöhemmin.",
            "Prosentteja tai euromääriä ei pidä päätellä ilman nimenomaista lähdetukea.",
        ),
        recommended_questions=(
            "Mihin suorituksiin maksuerät halutaan sitoa?",
            "Kuka hyväksyy maksuerän ennen laskutusta?",
            "Tarvitaanko erillinen maksuerätaulukko tarjouspyyntöön tai sopimukseen?",
        ),
    ),
    "wastewater_sewer": TopicTemplate(
        key_points=(
            "JV-laajuus kannattaa jakaa ainakin asuntohajotuksiin, pystylinjoihin, pohjaviemäriin ja tonttilinjaan, jos lähteet tukevat tätä jakoa.",
            "Pohjaviemärin, tonttilinjan ja pystylinjojen kuuluminen urakkaan pitää erottaa selvästi.",
            "Tarkempi arvio edellyttää määrätietoja, kuten asuntojen ja pystylinjojen määrää.",
        ),
        recommended_questions=(
            "Kuinka monta asuntoa ja JV-pystylinjaa kohteessa on?",
            "Kuuluuko pohjaviemäri urakkaan?",
            "Kuuluuko tonttilinja urakkaan?",
        ),
    ),
    "stormwater_sewer": TopicTemplate(
        key_points=(
            "SV-laajuus kannattaa erottaa pihan sadevesilinjoihin ja mahdollisiin katon kautta kulkeviin SV-linjoihin.",
            "Kattokaivot, SV-pystylinjat ja SV-pohjaviemäri pitää kirjata erikseen, jos ne kuuluvat urakkaan.",
            "Sadevesilinjojen työmäärää ei pidä päätellä ilman lähteissä näkyvää laajuutta.",
        ),
        recommended_questions=(
            "Kerätäänkö sadevesi myös katolta sisäisten SV-linjojen kautta?",
            "Kuuluuko urakkaan pihakaivoja tai SV-tonttilinjoja?",
            "Onko SV-laajuus kuvattu tarjouspyynnössä erikseen?",
        ),
    ),
    "boundaries": TopicTemplate(
        key_points=(
            "Urakkarajat pitää kirjata täsmällisesti ja erottaa, mikä kuuluu urakkaan ja mikä ei.",
            "JV, SV, pohjaviemäri, tonttilinja ja kaivot kannattaa käsitellä omina rajauskohtinaan.",
            "Epäselvä rajaus pitää ratkaista ennen hinnan tai vastuun tulkintaa.",
        ),
        recommended_questions=(
            "Mitkä linjat ja kaivot kuuluvat urakkaan?",
            "Missä urakka päättyy suhteessa kunnan liitoskohtaan?",
            "Mitä töitä on rajattu nimenomaisesti urakan ulkopuolelle?",
        ),
    ),
    "quality_video": TopicTemplate(
        key_points=(
            "Videotarkastus ja loppukuvaus kannattaa sitoa dokumentoituun laadunvarmistukseen.",
            "Kuvausten tarkastus ja kommentit kannattaa säilyttää myöhempää vastaanottoa ja takuuta varten.",
            "Standardivaatimuksia ei pidä väittää ilman suoraa lähdetukea.",
        ),
        recommended_questions=(
            "Mitä linjoja kuvataan ennen työtä ja työn jälkeen?",
            "Kuka tarkastaa kuvausten laadun?",
            "Miten kuvauskommentit liitetään vastaanotto- tai takuuasiakirjoihin?",
        ),
    ),
    "handover": TopicTemplate(
        key_points=(
            "Vastaanotossa kannattaa erottaa luovutettavat asiakirjat, todetut puutteet ja vastuiden siirtyminen.",
            "Avoimet puutteet pitää kirjata niin, että korjausvastuu ja määräaika ovat todennettavissa.",
            "Vastaanoton johtopäätöksiä ei pidä tehdä ilman lähteissä näkyvää vastaanottoaineistoa.",
        ),
        recommended_questions=(
            "Mitä asiakirjoja urakoitsija luovuttaa vastaanotossa?",
            "Mitä puutteita jäi avoimeksi?",
            "Milloin korjausten jälkitarkastus tehdään?",
        ),
    ),
    "warranty": TopicTemplate(
        key_points=(
            "Takuuasiat kannattaa sitoa dokumentoituihin havaintoihin, tarkastuksiin ja korjauspäätöksiin.",
            "Takuuajan ongelmat pitää kerätä niin, että ne voidaan yhdistää alkuperäiseen työn laatuun.",
            "Korjausvelvollisuutta ei pidä päätellä ilman lähdetukea.",
        ),
        recommended_questions=(
            "Mitä ongelmia on havaittu takuuajan aikana?",
            "Onko havaitut ongelmat yhdistetty videokuvauksiin tai valvojan kommentteihin?",
            "Mitä korjauksia urakoitsijalta vaaditaan takuuna?",
        ),
    ),
    "security_insurance": TopicTemplate(
        key_points=(
            "Vakuudet ja vakuutukset kannattaa kirjata sopimukseen todennettavina velvoitteina.",
            "Vakuuden määrästä tai kestosta ei pidä esittää lukua ilman suoraa lähdetukea.",
            "Vakuutusten kattavuus pitää tarkistaa suhteessa urakan riskeihin.",
        ),
        recommended_questions=(
            "Mitä vakuuksia sopimuksessa edellytetään?",
            "Mitä vakuutuksia urakoitsijalla pitää olla voimassa?",
            "Mihin asti vakuudet ovat voimassa?",
        ),
    ),
    "unit_prices_change_work": TopicTemplate(
        key_points=(
            "Lisätyöt ja yksikköhinnat kannattaa määritellä etukäteen ja dokumentoida ennen toteutusta.",
            "Yksikköhintaa ei pidä soveltaa uuteen työhön ilman lähteissä näkyvää perustetta.",
            "Muutostöiden hyväksyntätapa pitää olla jälkikäteen todennettavissa.",
        ),
        recommended_questions=(
            "Mille töille tarvitaan yksikköhinnat?",
            "Kuka hyväksyy lisätyön ennen toteutusta?",
            "Miten lisätyöt dokumentoidaan maksueriin?",
        ),
    ),
    "defects_issues": TopicTemplate(
        key_points=(
            "Puutteet, virheet ja reklamaatiot pitää dokumentoida havaintoina, vastuina ja korjaustilanteena.",
            "Korjausvaatimuksia ei pidä päätellä ilman lähteissä näkyvää havaintoa tai päätöstä.",
            "Puutelista kannattaa yhdistää vastaanottoon, jälkitarkastukseen tai takuuseen.",
        ),
        recommended_questions=(
            "Mitä puutteita on havaittu ja missä linjoissa?",
            "Kuka vastaa korjauksista?",
            "Miten korjausten valmistuminen todennetaan?",
        ),
    ),
}


def compose_answer(
    retrieval_packet: dict[str, Any],
    max_sources: int = 8,
    max_answer_bullets: int = 6,
) -> dict[str, Any]:
    sources = select_sources(retrieval_packet, max_sources=max_sources)
    answer_status = determine_answer_status(retrieval_packet, sources)
    topics = list(retrieval_packet.get("detected_topics") or [])
    missing_fields = list(retrieval_packet.get("missing_user_case_fields") or [])
    warnings = [clean_text(warning) for warning in retrieval_packet.get("warnings") or []]
    uncertainties = build_uncertainties(retrieval_packet, sources)

    key_points = build_key_points(topics, sources, max_answer_bullets)
    if answer_status == "insufficient_evidence":
        key_points = []

    answer = {
        "question": clean_text(retrieval_packet.get("question") or ""),
        "answer_scope": clean_text(retrieval_packet.get("answer_scope") or "general_cipp_user_case"),
        "answer_status": answer_status,
        "short_answer": build_short_answer(answer_status, topics, sources),
        "key_points": key_points,
        "source_based_notes": build_source_notes(sources, max_answer_bullets),
        "missing_user_case_fields": [clean_text(field) for field in missing_fields],
        "uncertainties": uncertainties,
        "recommended_next_questions": recommended_questions(topics, missing_fields),
        "sources": sources,
        "warnings": warnings,
        "generation_mode": GENERATION_MODE,
        "llm_used": LLM_USED,
    }
    return answer


def determine_answer_status(packet: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    retrieval_status = packet.get("retrieval_status")
    coverage_status = packet.get("evidence_coverage_status")
    text_context_count = int(packet.get("text_context_count") or 0)
    if retrieval_status == "no_results" or text_context_count == 0 or not sources:
        return "insufficient_evidence"
    if sources and all(source["source_strength"] == "weak" for source in sources):
        return "partial"
    if retrieval_status == "partial" or coverage_status != "ok":
        return "partial"
    return "answered"


def select_sources(packet: dict[str, Any], max_sources: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_type, key in (("clause", "clauses"), ("section", "sections"), ("raw_page", "raw_pages")):
        for row in packet.get(key) or []:
            status = row.get("text_context_status") or "missing"
            rows.append(
                {
                    "source_type": source_type,
                    "anonymized_reference_label": clean_text(row.get("reference_label") or "reference"),
                    "document_type": clean_text(row.get("document_type") or "unknown"),
                    "text_context_status": clean_text(status),
                    "snippet": clean_text(row.get("snippet") or ""),
                    "confidence": row.get("confidence") or row.get("source_confidence"),
                    "locator": source_locator(source_type, row),
                    "source_strength": "weak" if status == "topic_text_fallback" else "direct",
                }
            )
    rows = [row for row in rows if row["snippet"]]
    rows.sort(key=lambda row: (SOURCE_PRIORITY.get(row["text_context_status"], 99), row["source_type"], row["locator"]))
    return rows[:max_sources]


def build_short_answer(answer_status: str, topics: list[str], sources: list[dict[str, Any]]) -> str:
    if answer_status == "insufficient_evidence":
        return (
            "Retrieval-paketista ei löytynyt riittävää tekstilähdettä turvalliseen vastaukseen. "
            "En tee johtopäätöksiä ilman lähdekatkelmia."
        )
    topic_label = topic_summary(topics)
    source_count = len(sources)
    if answer_status == "partial":
        return (
            f"Aineisto antaa osittaisen tuen aiheeseen {topic_label}, mutta coverage ei ole täydellinen. "
            f"Alla olevat huomiot perustuvat {source_count} anonymisoituun lähdekatkelmaan, eikä niiden ulkopuolelta päätellä lisävaatimuksia."
        )
    return (
        f"Aineisto antaa lähdeperustaisen vastauksen aiheeseen {topic_label}. "
        f"Alla olevat huomiot perustuvat {source_count} anonymisoituun lähdekatkelmaan, ja vastaus rajataan retrieval-paketin sisältöön."
    )


def build_key_points(topics: list[str], sources: list[dict[str, Any]], max_bullets: int) -> list[str]:
    points: list[str] = []
    for topic in topics:
        template = TOPIC_TEMPLATES.get(topic)
        if not template:
            continue
        points.extend(template.key_points)
    if not points and sources:
        points.append("Valitut lähteet antavat aiheesta todennettavaa tekstikontekstia, mutta valmista topic-runkoa ei vielä ole.")
    return [clean_text(point) for point in unique_preserve_order(points)[:max_bullets]]


def build_source_notes(sources: list[dict[str, Any]], max_notes: int) -> list[str]:
    notes: list[str] = []
    for source in sources[:max_notes]:
        prefix = "Heikompi fallback-lähde" if source["source_strength"] == "weak" else "Lähdekatkelma"
        notes.append(
            clean_text(
                f"{prefix} ({source['anonymized_reference_label']} / {source['document_type']} / "
                f"{source['text_context_status']}): {source['snippet']}"
            )
        )
    return notes


def build_uncertainties(packet: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
    uncertainties: list[str] = []
    if packet.get("retrieval_status") != "ok":
        uncertainties.append("Retrieval-status ei ole ok, joten vastaus on vain osittain tuettu.")
    if packet.get("evidence_coverage_status") != "ok":
        uncertainties.append("Evidence coverage ei ole ok, joten kaikkia väitteitä ei voi vahvistaa tekstikatkelmista.")
    if packet.get("missing_text_context_count"):
        uncertainties.append("Osa evidence-riveistä jäi ilman suoraa tekstikontekstia.")
    if any(source["source_strength"] == "weak" for source in sources):
        uncertainties.append("Osa lähteistä on fallback-tasoisia eikä niitä käytetä vahvoina väitteinä.")
    if not sources:
        uncertainties.append("Retrieval-paketissa ei ollut käytettävää anonymisoitua lähdekatkelmaa.")
    if packet.get("missing_user_case_fields"):
        uncertainties.append("Tarkempi kohdekohtainen vastaus edellyttää puuttuvia käyttäjätietoja.")
    return [clean_text(item) for item in unique_preserve_order(uncertainties)]


def recommended_questions(topics: list[str], missing_fields: list[str]) -> list[str]:
    questions: list[str] = []
    if missing_fields:
        questions.append(f"Voitko täydentää nämä kohdetiedot: {', '.join(missing_fields)}?")
    for topic in topics:
        template = TOPIC_TEMPLATES.get(topic)
        if template:
            questions.extend(template.recommended_questions)
    if not questions:
        questions.append("Mitä asiakirjaa tai urakan osa-aluetta haluat tarkentaa seuraavaksi?")
    return [clean_text(question) for question in unique_preserve_order(questions)[:5]]


def topic_summary(topics: list[str]) -> str:
    if not topics:
        return "general_cipp"
    return ", ".join(clean_text(topic) for topic in topics)


def source_locator(source_type: str, row: dict[str, Any]) -> str:
    if source_type == "clause":
        return clean_text(row.get("clause_key") or row.get("title") or "clause")
    if source_type == "section":
        return clean_text(row.get("section_key") or row.get("title") or "section")
    page_no = row.get("page_no")
    return f"page {page_no}" if page_no is not None else "raw_page"


def render_markdown(answer: dict[str, Any]) -> str:
    lines = [
        "# Source-grounded answer",
        "",
        "## Question",
        clean_text(answer["question"]),
        "",
        "## Short answer",
        clean_text(answer["short_answer"]),
        "",
        "## Key points",
        numbered_or_none(answer["key_points"]),
        "",
        "## What the sources support",
        list_or_none(answer["source_based_notes"]),
        "",
        "## Missing information",
        list_or_none(answer["missing_user_case_fields"]),
        "",
        "## Uncertainties",
        list_or_none(answer["uncertainties"]),
        "",
        "## Suggested next questions",
        list_or_none(answer["recommended_next_questions"]),
        "",
        "## Sources",
    ]
    if answer["sources"]:
        for source in answer["sources"]:
            lines.append(
                "- "
                + clean_text(
                    f"[{source['anonymized_reference_label']} / {source['document_type']} / "
                    f"{source['text_context_status']}] {source['locator']}"
                )
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Generation",
            f"- mode: `{answer['generation_mode']}`",
            f"- llm_used: `{str(answer['llm_used']).lower()}`",
            f"- answer_status: `{answer['answer_status']}`",
        ]
    )
    return "\n".join(lines)


def write_outputs(answer: dict[str, Any], output: Path | None, output_md: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(answer, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(answer) + "\n", encoding="utf-8")


def load_retrieval_packet(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_packet_from_question(args: argparse.Namespace) -> dict[str, Any]:
    limits = RetrievalLimits()
    with psycopg.connect(database_url(args.db, args.env), row_factory=dict_row) as conn:
        return build_retrieval_packet(
            PostgresRetrievalRepository(conn),
            args.question,
            user_case=build_user_case(args),
            limits=limits,
        )


def clean_text(value: Any) -> str:
    text = sanitize_text(str(value or ""))
    text = re.sub(r"\b\d[\d\s.,]*\s*(?:€|eur|euroa?)", "[amount redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d[\d\s.,]*\s*e(?=/|\b)", "[amount redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\w)\+?\d[\d\s().–-]{6,}\d(?!\w)", "[phone redacted]", text)
    text = re.sub(r"[A-Z]:\\[^\s)]+", "[path redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def unique_preserve_order(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def numbered_or_none(values: list[str]) -> str:
    if not values:
        return "1. none"
    return "\n".join(f"{index}. {clean_text(value)}" for index, value in enumerate(values, start=1))


def list_or_none(values: list[str]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {clean_text(value)}" for value in values)


def main() -> None:
    parser = argparse.ArgumentParser()
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--question")
    input_group.add_argument("--retrieval-packet", type=Path)
    parser.add_argument("--user-case-json", type=Path)
    parser.add_argument("--apartments-count", type=int)
    parser.add_argument("--buildings-count", type=int)
    parser.add_argument("--staircases-count", type=int)
    parser.add_argument("--jv-verticals-count", type=int)
    parser.add_argument("--sv-verticals-count", type=int)
    parser.add_argument("--includes-bottom-drain", type=parse_bool)
    parser.add_argument("--includes-yard-line", type=parse_bool)
    parser.add_argument("--includes-video-inspection", type=parse_bool)
    parser.add_argument("--topic")
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--max-answer-bullets", type=int, default=6)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()

    packet = load_retrieval_packet(args.retrieval_packet) if args.retrieval_packet else build_packet_from_question(args)
    answer = compose_answer(packet, max_sources=args.max_sources, max_answer_bullets=args.max_answer_bullets)
    if not args.dry_run:
        write_outputs(answer, args.output, args.output_md)
    print(
        json.dumps(
            {
                "answer_status": answer["answer_status"],
                "llm_used": answer["llm_used"],
                "sources": len(answer["sources"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
