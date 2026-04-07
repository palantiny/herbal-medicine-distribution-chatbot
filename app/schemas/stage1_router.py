"""Stage1 LLM 라우터 구조화 출력 스키마."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GraphIntent = Literal[
    "SEARCH_TEMP",
    "SEARCH_TASTE",
    "SEARCH_MERIDIAN",
    "SEARCH_EFFICACY",
    "SEARCH_SYMPTOM",
    "SEARCH_FORMULA_CONTAINS",
    "SEARCH_CONTRAINDICATION",
    "SEARCH_DISTRIBUTION_ALL",
    "SEARCH_HERB_BY_MAKER",
    "SEARCH_HERB_BY_ORIGIN",
    "SEARCH_PRICE_INFO",
]

Stage1Route = Literal[
    "DIRECT_ANSWER",
    "SEARCH_GRAPH",
    "CALL_LLM2_SQL",
    "GENERATE_FINAL_ANSWER",
]


class ExtractedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: Literal[
        "Herb",
        "Formula",
        "NatureTemp",
        "NatureTaste",
        "Meridian",
        "Efficacy",
        "Symptom",
        "Maker",
        "Origin",
    ] = Field(description="추출된 노드의 종류")
    node_name: str = Field(description="추출된 노드의 실제 이름 (예: 감초, 두통, 영천)")


class RouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Stage1Route = Field(description="다음 행동 지시")
    reason: str = Field(description="해당 라우팅을 선택한 논리적 이유")
    target_intents: list[GraphIntent] = Field(
        description="실행할 그래프 탐색 경로 템플릿 (route가 SEARCH_GRAPH일 때만 사용)",
        default_factory=list,
    )
    extracted_nodes: list[ExtractedNode] = Field(
        description="질문에서 추출된 그래프 노드 목록",
        default_factory=list,
    )
    direct_response: str = Field(
        description="route가 DIRECT_ANSWER일 경우 사용자에게 바로 전달할 답변",
        default="",
    )
