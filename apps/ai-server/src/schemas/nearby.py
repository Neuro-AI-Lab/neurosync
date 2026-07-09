"""Schemas for the Nearby Facilities agent (HIRA hospitals/pharmacies + Kakao Map).

Contract mirrors docs/ai/api/hira_kakao_map_api_usage_guide.md §4 (Backend API contract).

Design:
- Two entity types: `hospital` (병원) and `pharmacy` (약국)
- Backend returns BOTH `places` (list for UI) AND `map.markers` (list for Kakao SDK)
  with the SAME `id` scheme (`hospital:{ykiho}` / `pharmacy:{ykiho}`)
- HIRA `XPos/YPos` → normalized `lng/lat` (crucial: XPos = longitude, YPos = latitude)
- `coordinate_source` tracks provenance (`hira` | `kakao_geocoded`)

Safety constraints (spec §10):
- `emergency_available=null` MUST NOT be treated as "available"
- `open_now=null` MUST NOT be treated as "open"
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput

EntityType = Literal["hospital", "pharmacy"]
CoordinateSource = Literal["hira", "kakao_geocoded"]


class Location(BaseModel):
    """Geographic point (WGS84)."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude (위도)")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude (경도)")

    model_config = ConfigDict(extra="forbid")


class Place(BaseModel):
    """Normalized facility record for UI listing.

    Field aliasing (HIRA → app):
        ykiho    → source_id
        yadmNm   → name / title
        addr     → address
        telno    → phone
        clCd/clCdNm     → type_code / type_name (hospital only)
        sidoCd/sidoCdNm → sido_code / sido_name
        sgguCd/sgguCdNm → sggu_code / sggu_name
        XPos     → lng (경도)
        YPos     → lat (위도)
    """

    id: str = Field(..., description="Composite id: '{entity_type}:{source_id}'")
    entity_type: EntityType
    source_id: str = Field(..., description="HIRA ykiho or upstream identifier")
    name: str
    title: str = Field(default="", description="Marker title (usually == name)")
    address: str = ""
    phone: str = ""

    # Hospital-specific (nullable for pharmacy)
    type_code: str | None = None
    type_name: str | None = None
    subject_code: str | None = None
    subject_name: str | None = None

    # Common
    sido_code: str | None = None
    sido_name: str | None = None
    sggu_code: str | None = None
    sggu_name: str | None = None

    # Coordinates
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)
    latitude: float | None = None  # alias for legacy consumers
    longitude: float | None = None
    coordinate_source: CoordinateSource | None = None

    # Distance from user query point (nullable)
    distance_km: float | None = Field(default=None, ge=0.0)

    # Safety flags — MUST be nullable per spec §10 (never treat null as True)
    emergency_available: bool | None = None
    open_now: bool | None = None
    night_service_available: bool | None = None
    holiday_service_available: bool | None = None

    model_config = ConfigDict(extra="ignore")


class Marker(BaseModel):
    """Slim marker payload for Kakao Map SDK.

    Rendered by frontend as `new kakao.maps.Marker(...)`. Kakao expects
    `LatLng(lat, lng)` — pass in that order.
    """

    id: str = Field(..., description="Matches Place.id — enables list↔marker sync")
    entity_type: EntityType
    title: str
    address: str = ""
    phone: str = ""
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    distance_km: float | None = Field(default=None, ge=0.0)
    coordinate_source: CoordinateSource = "hira"

    model_config = ConfigDict(extra="forbid")


class MapPayload(BaseModel):
    """Container for Kakao Map SDK consumption."""

    provider: Literal["kakao"] = "kakao"
    coordinate_source: str = "HIRA XPos/YPos"
    markers: list[Marker] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SourceMeta(BaseModel):
    """Per-source (hospital/pharmacy) request metadata."""

    result_code: str = ""
    result_msg: str = ""
    format: Literal["json", "xml"] = "json"
    page_no: int = 1
    num_of_rows: int = 0
    total_count: int = 0
    returned_count: int = 0
    normalized_count: int = 0
    pages_fetched: int = 1
    truncated: bool = False

    model_config = ConfigDict(extra="ignore")


# ── Input schemas ────────────────────────────────────────────────────


class NearbySearchInput(AgentInput):
    """Input for a single-page nearby search (hospital OR pharmacy)."""

    entity_type: EntityType
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)
    radius_km: float | None = Field(default=None, ge=0.0, le=100.0)
    name: str | None = Field(default=None, description="병원명·약국명 검색어 (yadmNm)")
    sido_code: str | None = None
    sggu_code: str | None = None
    subject_code: str | None = Field(
        default=None, description="진료과목 (hospital only)"
    )
    hospital_type_code: str | None = Field(
        default=None, description="의료기관 종별 (hospital only)"
    )
    page_no: int = Field(default=1, ge=1)
    num_of_rows: int = Field(default=20, ge=1, le=1000)


class NearbyReportInput(AgentInput):
    """Input for a multi-page report (aggregated pages up to max_pages)."""

    entity_type: EntityType
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)
    radius_km: float | None = Field(default=None, ge=0.0, le=100.0)
    num_of_rows: int = Field(default=1000, ge=1, le=1000)
    max_pages: int = Field(default=10, ge=1, le=100)


# ── Output ───────────────────────────────────────────────────────────


class NearbyResponse(AgentOutput):
    """Backend response for /ai/nearby/*.

    Structure per spec §4.
    """

    generated_at: str = Field(default="", description="ISO8601 UTC")
    source: Literal["HIRA"] = "HIRA"
    query: dict = Field(default_factory=dict, description="Echo of input parameters")
    sources: dict[str, SourceMeta] = Field(
        default_factory=dict,
        description="Per-entity source metadata: {'hospital': {...}} or {'pharmacy': {...}}",
    )
    places: list[Place] = Field(default_factory=list)
    map: MapPayload = Field(default_factory=MapPayload)
    notice: str = Field(
        default="",
        description=(
            "Free-form advisory. E.g. HIRA basic info only; emergency/night hours "
            "require additional data sources."
        ),
    )

    model_config = ConfigDict(extra="ignore")


# ── Constants exposed for the agent ──────────────────────────────────

DEFAULT_NOTICE_HOSPITAL = (
    "병원 기본 정보입니다. 응급 가능 여부는 HIRA 병원 기본정보만으로 확정하지 않습니다."
)
DEFAULT_NOTICE_PHARMACY = (
    "약국 기본 정보입니다. 현재 영업 중, 심야 운영, 휴일 운영 여부는 "
    "HIRA 약국 기본정보만으로 확정하지 않습니다."
)
