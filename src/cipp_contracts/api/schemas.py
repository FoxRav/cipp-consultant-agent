from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apartments_count: int | None = Field(default=None, ge=0)
    buildings_count: int | None = Field(default=None, ge=0)
    staircases_count: int | None = Field(default=None, ge=0)
    jv_verticals_count: int | None = Field(default=None, ge=0)
    sv_verticals_count: int | None = Field(default=None, ge=0)
    includes_bottom_drain: bool | None = None
    includes_yard_line: bool | None = None
    includes_stormwater: bool | None = None
    includes_roof_drains: bool | None = None
    includes_video_inspection: bool | None = None
    includes_unit_prices: bool | None = None


class AnswerOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_sources: int = Field(default=8, ge=1, le=20)
    include_retrieval_packet: bool = False
    include_debug: bool = False


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=1000)
    user_case: UserCase = Field(default_factory=UserCase)
    options: AnswerOptions = Field(default_factory=AnswerOptions)


class HealthResponse(BaseModel):
    status: str
    service: str
    llm_enabled: bool


class SuggestedQuestion(BaseModel):
    topic_code: str
    label: str
    question: str


class AppConfigResponse(BaseModel):
    environment: str
    llm_enabled: bool
    user_case_fields: list[dict[str, Any]]
    defaults: dict[str, Any]
    topics: list[dict[str, str]]
    ui_labels: dict[str, str]

