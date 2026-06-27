from __future__ import annotations

import json

from fastapi.testclient import TestClient

from cipp_contracts.api.dev_server import create_app


def fake_answer_service(captured: list[dict[str, object]] | None = None):
    def _service(request):
        user_case = request.user_case.model_dump(exclude_none=True)
        if captured is not None:
            captured.append(user_case)
        return {
            "question": request.question,
            "answer_scope": "general_cipp_user_case",
            "answer_status": "partial",
            "short_answer": "Aineisto antaa osittaisen lähdeperustaisen vastauksen.",
            "key_points": ["JV-laajuus pitää erottaa pystylinjoihin ja pohjaviemäriin."],
            "source_based_notes": ["Lähdekatkelma (reference_001 / rfq / direct_section): työ kuvataan."],
            "missing_user_case_fields": ["includes_yard_line"],
            "uncertainties": ["Tarkempi vastaus edellyttää tonttilinjan rajausta."],
            "recommended_next_questions": ["Kuuluuko tonttilinja urakkaan?"],
            "sources": [
                {
                    "anonymized_reference_label": "reference_001",
                    "document_type": "rfq",
                    "source_type": "section",
                    "source_class": "retrieval_evidence",
                    "text_context_status": "direct_section",
                    "confidence": 1.0,
                    "snippet": "Työ koskee C:\\secret\\data\\raw\\As Oy Salainen\\urakka.pdf linjoja.",
                    "locator": "section",
                    "source_strength": "direct",
                }
            ],
            "warnings": [],
            "generation_mode": "deterministic_source_grounded",
            "llm_used": False,
        }

    return _service


def client(captured: list[dict[str, object]] | None = None) -> TestClient:
    return TestClient(create_app(answer_service=fake_answer_service(captured)))


def answer_payload() -> dict[str, object]:
    return {
        "question": "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?",
        "user_case": {
            "apartments_count": 30,
            "buildings_count": 1,
            "staircases_count": 3,
            "jv_verticals_count": 8,
            "sv_verticals_count": 2,
            "includes_bottom_drain": True,
            "includes_yard_line": False,
            "includes_stormwater": False,
            "includes_roof_drains": False,
            "includes_video_inspection": True,
            "includes_unit_prices": True,
        },
        "options": {"max_sources": 8, "include_retrieval_packet": False, "include_debug": False},
    }


def test_health_endpoint() -> None:
    response = client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cipp-consultant-agent-dev-api",
        "llm_enabled": False,
    }


def test_app_config_returns_user_case_fields() -> None:
    response = client().get("/api/app-config")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "local_dev"
    assert body["llm_enabled"] is False
    assert any(field["name"] == "apartments_count" for field in body["user_case_fields"])


def test_suggested_questions_returns_core_questions() -> None:
    response = client().get("/api/suggested-questions")

    assert response.status_code == 200
    questions = response.json()["questions"]
    assert any(question["topic_code"] == "payment" for question in questions)
    assert any(question["topic_code"] == "amateur_operator_guidance" for question in questions)


def test_answer_endpoint_returns_composer_answer() -> None:
    response = client().post("/api/answer", json=answer_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["api_status"] == "ok"
    assert body["request_id"]
    assert body["duration_ms"] >= 0
    assert body["answer_status"] == "partial"


def test_llm_used_is_false() -> None:
    body = client().post("/api/answer", json=answer_payload()).json()

    assert body["llm_used"] is False


def test_user_case_parameters_are_passed_to_composer() -> None:
    captured: list[dict[str, object]] = []

    response = client(captured).post("/api/answer", json=answer_payload())

    assert response.status_code == 200
    assert captured[0]["apartments_count"] == 30
    assert captured[0]["jv_verticals_count"] == 8
    assert captured[0]["includes_bottom_drain"] is True


def test_api_does_not_return_windows_paths_or_real_project_names() -> None:
    body = client().post("/api/answer", json=answer_payload()).json()
    serialized = json.dumps(body, ensure_ascii=False)

    assert "C:\\secret" not in serialized
    assert "data\\raw" not in serialized
    assert "As Oy Salainen" not in serialized
    assert "[path redacted]" in serialized


def test_missing_user_case_fields_are_visible() -> None:
    body = client().post("/api/answer", json=answer_payload()).json()

    assert "includes_yard_line" in body["missing_user_case_fields"]
    assert body["uncertainties"]
