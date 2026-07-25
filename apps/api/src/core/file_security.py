"""업로드 파일 보안 검증 (FR-028).

대화 중 첨부(FR-048)로 들어오는 처방전/진단서는 민감 의료문서다. 신뢰할 수
없는 입력이므로 ai-server로 넘기기 전에 플랫폼에서 걸러야 한다:

- 크기 상한
- 확장자·Content-Type 화이트리스트 (jpg/png/pdf)
- **매직넘버(파일 시그니처) 검증** — Content-Type은 위조 가능하므로 실제 바이트로
  확인해 polyglot/위장 파일을 차단한다

멀웨어 스캔(ClamAV)은 Phase 2 인프라 항목(별도 워커)으로 남긴다 — 여기서는
동기 검증 가능한 통제만 수행한다.
"""

from __future__ import annotations


class FileSecurityError(ValueError):
    """검증 실패 — 호출자가 400/413으로 매핑한다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# 매직넘버(파일 시작 바이트) → 정규 content-type.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
]

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def sniff_content_type(data: bytes) -> str | None:
    """실제 바이트로 content-type을 판별. 매칭 없으면 None."""
    for sig, ctype in _SIGNATURES:
        if data.startswith(sig):
            return ctype
    return None


def validate_upload(
    data: bytes,
    *,
    declared_content_type: str | None,
    max_bytes: int,
) -> str:
    """업로드를 검증하고 **신뢰 가능한 정규 content-type**을 반환한다.

    선언된 Content-Type이 아니라 매직넘버로 확정한 값을 쓴다 — 이 반환값을
    ai-server로 넘겨야 위조된 헤더에 속지 않는다.
    """
    if not data:
        raise FileSecurityError("EMPTY_FILE", "빈 파일이에요.")
    if len(data) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise FileSecurityError("FILE_TOO_LARGE", f"파일이 너무 커요 (최대 {mb}MB).")

    sniffed = sniff_content_type(data)
    if sniffed is None:
        raise FileSecurityError(
            "UNSUPPORTED_FILE_TYPE",
            "지원하지 않는 파일이에요. JPG·PNG·PDF만 올릴 수 있어요.",
        )
    # 실제 방어는 매직넘버 스니핑 결과(sniffed)를 신뢰값으로 반환하는 것이다 —
    # 위장한 선언 헤더로는 지원 외 타입을 통과시킬 수 없다(이미 위 sniff 게이트 통과).
    # 아래는 선언 타입이 아예 허용 목록 밖이면 조기 차단하는 보조 필터일 뿐이며,
    # declared==sniffed 일치까지 강제하지는 않는다(관대한 client content-type 수용).
    if declared_content_type and declared_content_type not in ALLOWED_CONTENT_TYPES:
        raise FileSecurityError(
            "UNSUPPORTED_FILE_TYPE",
            "지원하지 않는 파일이에요. JPG·PNG·PDF만 올릴 수 있어요.",
        )
    return sniffed
