"""마이헬스웨이 PHR JSON 로더 (source-agnostic).

v1: 로컬 파일 경로만 지원. Phase 3에서 PHR API 호출을 동일 인터페이스로 확장.

로더 책임 (Layer 1 — 원본 편차 방어):
- JSON 로드 · 컨테이너 검증 (`publicData` 존재)
- 리소스 유형별 원시 필드 추출 (dict → dict)
- 민감정보 마스킹 헬퍼 (`redact_for_log`)

**Neuro-Sync 도메인 스키마로의 변환은 이 어댑터가 하지 않는다** —
`agents/patient_history.py`가 원시 dict를 받아 `PhrSummary`로 반환한다.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.adapters.base import VendorAdapter

logger = logging.getLogger(__name__)


class MyHealthWayReadError(Exception):
    """PHR 파일 파싱 실패."""


class MyHealthWayReader(VendorAdapter):
    """`myhealthway.go.kr` 계열 PHR bundle을 로드해 raw dict 목록으로 반환.

    실 샘플 관찰:
    - 최상위: `{"publicData": [...], "medicalData": [...], "healthData": {...}}`
    - `publicData`의 각 entry: `{"resource": {...}}` 래퍼
    - Bundle이 아닌 커스텀 컨테이너이므로 표준 FHIR Bundle 파서 사용 불가
    """

    @property
    def adapter_name(self) -> str:
        return "myhealthway-reader"

    async def healthcheck(self) -> bool:
        """파일 소스는 항상 True. API 소스 확장 시 이 시점에서 검증."""
        return True

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        """이름·주민번호 등 PII 마스킹 (로그 안전).

        - `name` → "[REDACTED_NAME]"
        - `identifier[NNKOR].value` → "[REDACTED_RN]"
        기타 필드는 그대로 (요양기관명 · 주소는 임상적으로 유용).
        """
        return _redact(payload)

    async def load_bundle(self, source: str | Path) -> dict[str, Any]:
        """PHR JSON 파일을 raw dict로 로드.

        Raises:
            MyHealthWayReadError: 파일 미존재 · JSON 파싱 실패 ·
                `publicData` 키 부재.
        """
        path = Path(source)
        if not path.is_file():
            raise MyHealthWayReadError(f"PHR file not found: {path}")
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise MyHealthWayReadError(f"Invalid JSON: {path}: {exc}") from exc
        if not isinstance(data, dict) or "publicData" not in data:
            raise MyHealthWayReadError(
                f"PHR file missing 'publicData' key: {path}"
            )
        logger.info(
            "myhealthway-reader loaded %s (%d publicData entries)",
            path.name,
            len(data.get("publicData") or []),
        )
        return data

    def iter_resources(
        self,
        bundle: dict[str, Any],
        resource_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """`publicData` 순회하며 리소스 dict 목록 반환. 유형 필터 옵션.

        - entry가 `{"resource": {...}}` 형태여야 함. 아니면 스킵.
        - `resource_type` 지정 시 `resourceType == resource_type`만.
        """
        out: list[dict[str, Any]] = []
        for entry in bundle.get("publicData") or []:
            if not isinstance(entry, dict):
                continue
            resource = entry.get("resource")
            if not isinstance(resource, dict):
                continue
            if resource_type and resource.get("resourceType") != resource_type:
                continue
            out.append(resource)
        return out

    @staticmethod
    def compute_name_hash(name: str | None) -> str:
        """성명 → sha256[:16]. 원문 저장 방지용 안정 해시."""
        if not name:
            return ""
        return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


# ── Internal helpers ─────────────────────────────────────────────────


def _redact(obj: Any) -> Any:
    """재귀적으로 이름·주민번호 필드 마스킹."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "name" and isinstance(v, list):
                out[k] = [{"text": "[REDACTED_NAME]"} for _ in v]
            elif k == "identifier" and isinstance(v, list):
                out[k] = [_redact_identifier(i) for i in v]
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _redact_identifier(ident: Any) -> Any:
    if not isinstance(ident, dict):
        return ident
    result = dict(ident)
    # 주민번호(NNKOR) 마스킹
    type_coding = ((ident.get("type") or {}).get("coding") or [{}])[0]
    if type_coding.get("code") == "NNKOR":
        result["value"] = "[REDACTED_RN]"
    return result
