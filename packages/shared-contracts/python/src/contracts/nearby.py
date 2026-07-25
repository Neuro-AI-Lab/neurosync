"""GET /ai/nearby/hospitals — 병원 검색 응답 (플랫폼이 소비하는 부분만).

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.

ai-server가 HIRA 조회 + 카카오 지오코딩으로 좌표를 채운 병원 목록을 반환한다.
플랫폼(apps/api)은 이 좌표로 카카오맵 HTML을 렌더한다 — 지도 렌더는 플랫폼
책임, 데이터 조회는 ai-server 책임(FR-049).

ai-server 응답은 이보다 필드가 많으므로 `extra="ignore"`로 필요한 것만 취한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NearbyPlace(BaseModel):
    name: str = ""
    lat: float | None = None
    lng: float | None = None
    address: str = ""
    phone: str = ""
    distance_km: float | None = None
    type_name: str | None = None

    model_config = ConfigDict(extra="ignore")


class NearbyHospitalsResponse(BaseModel):
    places: list[NearbyPlace] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")
