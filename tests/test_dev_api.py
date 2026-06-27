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


def failing_client() -> TestClient:
    def _service(_request):
        raise RuntimeError("synthetic composer failure")

    return TestClient(create_app(answer_service=_service))


def answer_payload() -> dict[str, object]:
    return {
        "question": "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?",
        "user_case": {
            "apartments_count": 30,
            "buildings_count": 1,
            "staircases_count": 3,
            "jv_verticals_count": 15,
            "sv_verticals_count": 4,
            "roof_drains_count": 4,
            "bottom_drain_length_m": 50,
            "yard_line_length_m": 30,
            "stormwater_line_length_m": 30,
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
    field_names = [field["name"] for field in body["user_case_fields"]]
    assert field_names == [
        "apartments_count",
        "buildings_count",
        "staircases_count",
        "jv_verticals_count",
        "sv_verticals_count",
        "roof_drains_count",
        "bottom_drain_length_m",
        "yard_line_length_m",
        "stormwater_line_length_m",
    ]
    defaults = body["defaults"]
    assert defaults["sv_verticals_count"] == 4
    assert defaults["roof_drains_count"] == defaults["sv_verticals_count"]
    assert defaults["stormwater_line_length_m"] == 30
    labels = {field["label"] for field in body["user_case_fields"]}
    assert "Videotarkastus" not in labels
    assert "Yksikköhinnat / lisätyöt" not in labels
    assert "includes_video_inspection" not in field_names
    assert "includes_unit_prices" not in field_names


def test_suggested_questions_returns_core_questions() -> None:
    response = client().get("/api/suggested-questions")

    assert response.status_code == 200
    questions = response.json()["questions"]
    assert any(question["topic_code"] == "payment" for question in questions)
    assert any(question["topic_code"] == "amateur_operator_guidance" for question in questions)
    labels = {question["label"] for question in questions}
    assert "Videotarkastus" not in labels
    assert "Lisätyöt" not in labels


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
    assert captured[0]["jv_verticals_count"] == 15
    assert captured[0]["sv_verticals_count"] == 4
    assert captured[0]["roof_drains_count"] == 4
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


def test_answer_endpoint_returns_json_error_without_stack_trace() -> None:
    response = failing_client().post("/api/answer", json=answer_payload())

    assert response.status_code == 500
    body = response.json()
    assert body["api_status"] == "error"
    assert body["error_code"] == "answer_composer_failed"
    assert body["request_id"]
    serialized = json.dumps(body, ensure_ascii=False)
    assert "synthetic composer failure" not in serialized
    assert "Traceback" not in serialized
