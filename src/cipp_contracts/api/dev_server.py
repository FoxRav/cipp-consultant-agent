from __future__ import annotations

import argparse
import logging
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

from cipp_contracts.answer.compose_answer import compose_answer
from cipp_contracts.config import database_url
from cipp_contracts.retrieve.build_retrieval_packet import (
    PostgresRetrievalRepository,
    RetrievalLimits,
    build_retrieval_packet,
    sanitize_text,
)

from .schemas import AnswerRequest, AppConfigResponse, HealthResponse, SuggestedQuestion


SERVICE_NAME = "cipp-consultant-agent-dev-api"
LLM_ENABLED = False
ENVIRONMENT = "local_dev"
LOGGER = logging.getLogger(__name__)

QUESTION_SUGGESTIONS = [
    SuggestedQuestion(
        topic_code="payment",
        label="Maksuerät",
        question="Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?",
    ),
    SuggestedQuestion(
        topic_code="wastewater_scope",
        label="JV ja pohjaviemäri",
        question="Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?",
    ),
    SuggestedQuestion(
        topic_code="stormwater_scope",
        label="SV ja kattokaivot",
        question="Mitä pitää huomioida sadevesilinjojen ja kattokaivojen sukituksessa?",
    ),
    SuggestedQuestion(
        topic_code="boundaries",
        label="Urakkarajat",
        question="Mitä urakkarajoissa pitää huomioida ja miten määritellään mikä kuuluu urakkaan?",
    ),
    SuggestedQuestion(
        topic_code="handover",
        label="Vastaanotto",
        question="Mitä vastaanotossa pitää tarkistaa ennen CIPP-urakan hyväksymistä?",
    ),
    SuggestedQuestion(
        topic_code="warranty",
        label="Takuu",
        question="Miten takuuasiat kannattaa kirjata CIPP-sukitusurakassa?",
    ),
    SuggestedQuestion(
        topic_code="security_insurance",
        label="Vakuudet",
        question="Mitä vakuuksia ja vakuutuksia CIPP-urakassa pitää huomioida?",
    ),
    SuggestedQuestion(
        topic_code="defects_claims",
        label="Puutteet",
        question="Miten puutteet, virheet ja reklamaatiot pitää dokumentoida CIPP-urakassa?",
    ),
    SuggestedQuestion(
        topic_code="project_planning",
        label="Hankesuunnittelu",
        question="Miten taloyhtiön kannattaa valmistella putkiremontin hankesuunnittelu?",
    ),
    SuggestedQuestion(
        topic_code="board_preparation",
        label="Hallitus",
        question="Mitä hallituksen pitää valmistella ennen sukitusurakan tarjouspyyntöä?",
    ),
    SuggestedQuestion(
        topic_code="amateur_operator_guidance",
        label="Muistilista",
        question="Mitä amatööritoimijan pitää muistaa ennen CIPP-sukitusurakan käynnistämistä?",
    ),
]

USER_CASE_FIELD_CONFIG = [
    {"name": "apartments_count", "label": "Asuntoja", "type": "number", "default": 30},
    {"name": "buildings_count", "label": "Rakennuksia", "type": "number", "default": 1},
    {"name": "staircases_count", "label": "Porrashuoneita", "type": "number", "default": 3},
    {"name": "jv_verticals_count", "label": "JV-pystyviemäreitä", "type": "number", "default": 15},
    {"name": "sv_verticals_count", "label": "SV-pystyviemäreitä", "type": "number", "default": 4},
    {"name": "roof_drains_count", "label": "Kattokaivot", "type": "number", "default": 4},
    {"name": "bottom_drain_length_m", "label": "Pohjaviemäri m", "type": "number", "default": 50},
    {"name": "yard_line_length_m", "label": "Tonttilinja m", "type": "number", "default": 30},
    {"name": "stormwater_line_length_m", "label": "Sadevesilinjat m", "type": "number", "default": 30},
]

UI_LABELS = {
    "answered": "Vastattu",
    "partial": "Osittainen",
    "insufficient_evidence": "Ei riittävää näyttöä",
    "llm_used": "LLM käytössä",
    "expert_guidance": "Asiantuntijaohje",
    "source_grounded": "Lähdeperustainen",
}

AnswerService = Callable[[AnswerRequest], dict[str, Any]]


def create_app(answer_service: AnswerService | None = None) -> FastAPI:
    app = FastAPI(title="CIPP Consultant Agent Dev API", version="0.7.0-dev")
    app.state.answer_service = answer_service or compose_from_database
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": SERVICE_NAME, "llm_enabled": LLM_ENABLED}

    @app.get("/api/suggested-questions")
    def suggested_questions() -> dict[str, Any]:
        return {"questions": [question.model_dump() for question in QUESTION_SUGGESTIONS]}

    @app.get("/api/app-config", response_model=AppConfigResponse)
    def app_config() -> dict[str, Any]:
        return {
            "environment": ENVIRONMENT,
            "llm_enabled": LLM_ENABLED,
            "user_case_fields": USER_CASE_FIELD_CONFIG,
            "defaults": {
                field["name"]: field["default"]
                for field in USER_CASE_FIELD_CONFIG
                if "default" in field
            },
            "topics": [
                {"topic_code": question.topic_code, "label": question.label}
                for question in QUESTION_SUGGESTIONS
            ],
            "ui_labels": UI_LABELS,
        }

    @app.post("/api/answer")
    def answer(request: AnswerRequest) -> Any:
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        user_case = request.user_case.model_dump(exclude_none=True)
        LOGGER.info(
            "api_answer_start request_id=%s endpoint=/api/answer question_length=%s user_case_keys=%s",
            request_id,
            len(request.question),
            sorted(user_case.keys()),
        )
        try:
            payload = app.state.answer_service(request)
            payload = sanitize_api_payload(payload)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            payload.update(
                {
                    "api_status": "ok",
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                }
            )
            LOGGER.info(
                "api_answer_success request_id=%s endpoint=/api/answer duration_ms=%s",
                request_id,
                duration_ms,
            )
            return payload
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            LOGGER.exception(
                "api_answer_error request_id=%s endpoint=/api/answer duration_ms=%s",
                request_id,
                duration_ms,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "api_status": "error",
                    "error_code": "answer_composer_failed",
                    "message": "Answer composer failed. See backend logs for details.",
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                },
            )

    return app


def compose_from_database(request: AnswerRequest) -> dict[str, Any]:
    user_case = request.user_case.model_dump(exclude_none=True)
    limits = RetrievalLimits(sections=max(20, request.options.max_sources * 3))
    with psycopg.connect(database_url(None, Path(".env")), row_factory=dict_row) as conn:
        packet = build_retrieval_packet(
            PostgresRetrievalRepository(conn),
            request.question,
            user_case=user_case,
            limits=limits,
        )
    answer = compose_answer(packet, max_sources=request.options.max_sources)
    if request.options.include_retrieval_packet or request.options.include_debug:
        answer["retrieval_packet"] = packet
    if request.options.include_debug:
        answer["debug"] = {
            "retrieval_status": packet.get("retrieval_status"),
            "detected_topics": packet.get("detected_topics", []),
            "evidence_coverage_status": packet.get("evidence_coverage_status"),
            "text_context_count": packet.get("text_context_count"),
        }
    return answer


def sanitize_api_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {sanitize_key(key): sanitize_api_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_api_payload(item) for item in value]
    if isinstance(value, str):
        return sanitize_api_text(value)
    return value


def sanitize_key(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_:-]", "_", str(value))


def sanitize_api_text(value: str) -> str:
    text = re.sub(
        r"[A-Z]:\\[^\"')]+?\.(?:pdf|docx?|xlsx?|xls|dwg|txt)",
        "[path redacted]",
        value,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[A-Z]:\\[^\s\"')]+", "[path redacted]", text)
    text = re.sub(r"\bdata[/\\]raw[/\\][^\s\"')]+", "[raw path redacted]", text, flags=re.IGNORECASE)
    text = sanitize_text(text)
    text = re.sub(r"[A-Z]:\\[^\s\"')]+", "[path redacted]", text)
    text = re.sub(r"\bdata[/\\]raw[/\\][^\s\"')]+", "[raw path redacted]", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(?:As(?:unto)?\.?\s+Oy|AOY)\s+[A-ZÅÄÖ][A-Za-zÅÄÖåäö0-9 .'-]{2,60}",
        "As Oy [redacted]",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run("cipp_contracts.api.dev_server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
