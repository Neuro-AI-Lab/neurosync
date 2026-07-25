"""F4 temporal 계약 — ai-server(snake_case) ↔ 모바일(camelCase) 케이싱 회귀.

리포트 점수 추이 차트(핸드오프 수정 7)는 이 계약으로 바인딩된다. 과거 OCR/도메인
프록시에서 snake_case↔camelCase 불일치로 필드가 통째로 비었던 사고가 있었으므로,
`/report/trend`가 의존하는 왕복(파싱=필드명, 직렬화=camelCase alias)을 고정한다.
"""

from __future__ import annotations

from contracts.temporal import TemporalSummarizeRequest, TemporalSummarizeResponse


def test_response_parses_snake_and_emits_camel() -> None:
    # ai-server TemporalSummaryOutput 흉내 — 여분 필드 포함(extra="ignore").
    raw = {
        "overall_direction": "improved",
        "domain_trends": [{"domain": "depression"}],  # 프록시가 버리는 여분 필드
        "new_symptoms": [],
        "plot_data": [
            {
                "date": "2026-05-14",
                "phq9": 18,
                "gad7": 15,
                "ctrs_level": 2,
                "sentiment_polarity": -0.42,
                "events": ["첫 방문"],
            },
            {"date": "2026-07-19", "phq9": 9, "gad7": 7, "ctrs_level": 3},
        ],
        "is_first_visit": False,
    }

    parsed = TemporalSummarizeResponse.model_validate(raw)
    assert parsed.overall_direction == "improved"
    assert len(parsed.plot_data) == 2
    assert parsed.plot_data[0].ctrs_level == 2  # 필드명으로 파싱

    out = parsed.model_dump(by_alias=True, mode="json")
    # 모바일이 소비하는 camelCase 키
    assert out["overallDirection"] == "improved"
    assert out["isFirstVisit"] is False
    p0 = out["plotData"][0]
    assert p0["ctrsLevel"] == 2
    assert p0["sentimentPolarity"] == -0.42
    assert p0["phq9"] == 18
    # 여분 필드는 새어나가지 않는다 (NFR v3-2: 도메인/질환 문자열 비노출)
    assert "domain_trends" not in out
    assert "domainTrends" not in out


def test_request_defaults_first_visit_when_no_prior() -> None:
    req = TemporalSummarizeRequest(
        session_id="s1",
        patient_id="p1",
        is_first_visit=True,
        current_scales={"PHQ-9": 12},
        current_date="2026-07-19",
    )
    body = req.model_dump(mode="json")
    assert body["current_scales"] == {"PHQ-9": 12}
    assert body["prior_scales"] == {}
    assert body["is_first_visit"] is True
