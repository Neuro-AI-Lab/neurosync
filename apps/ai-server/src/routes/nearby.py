"""GET /ai/nearby/{hospitals,pharmacies,ui} — HIRA 기반 근처 시설 검색 + 데모 UI.

Contract: docs/ai/api/hira_kakao_map_api_usage_guide.md §4.

- `search` 엔드포인트: 단일 페이지 결과 (기본 사용)
- `report` 엔드포인트: 다중 페이지 aggregate (대량 조회)
- `/ui` : Kakao Map 데모 페이지 (개발/데모용)
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.agents.nearby_facilities import NearbyFacilitiesAgent
from src.dependencies import get_nearby_agent, get_settings
from src.schemas.nearby import (
    NearbyReportInput,
    NearbyResponse,
    NearbySearchInput,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/nearby", tags=["nearby"])


# ── /ai/nearby/hospitals ─────────────────────────────────────────────


@router.get("/hospitals", response_model=NearbyResponse)
async def search_hospitals(
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lng: float | None = Query(default=None, ge=-180.0, le=180.0),
    radius_km: float | None = Query(default=None, ge=0.0, le=100.0),
    name: str | None = Query(default=None, description="병원명 검색어 (yadmNm)"),
    sido_code: str | None = Query(default=None),
    sggu_code: str | None = Query(default=None),
    subject_code: str | None = Query(default=None, description="진료과목 코드"),
    hospital_type_code: str | None = Query(default=None, description="의료기관 종별 코드"),
    page_no: int = Query(default=1, ge=1),
    num_of_rows: int = Query(default=20, ge=1, le=1000),
    session_id: str | None = Query(default=None),
    agent: NearbyFacilitiesAgent = Depends(get_nearby_agent),
) -> NearbyResponse:
    """단일 페이지 병원 검색."""
    request_id = str(uuid.uuid4())
    logger.info(
        "nearby/hospitals request_id=%s lat=%s lng=%s radius=%s page=%d rows=%d",
        request_id, lat, lng, radius_km, page_no, num_of_rows,
    )

    inp = NearbySearchInput(
        session_id=session_id or f"nearby-{request_id[:8]}",
        request_id=request_id,
        entity_type="hospital",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        name=name,
        sido_code=sido_code,
        sggu_code=sggu_code,
        subject_code=subject_code,
        hospital_type_code=hospital_type_code,
        page_no=page_no,
        num_of_rows=num_of_rows,
    )
    try:
        return await agent.search(inp)
    except Exception as exc:
        logger.error("nearby/hospitals failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="HIRA upstream failure") from exc


@router.get("/hospitals/report", response_model=NearbyResponse)
async def report_hospitals(
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lng: float | None = Query(default=None, ge=-180.0, le=180.0),
    radius_km: float | None = Query(default=None, ge=0.0, le=100.0),
    num_of_rows: int = Query(default=1000, ge=1, le=1000),
    max_pages: int = Query(default=10, ge=1, le=100),
    session_id: str | None = Query(default=None),
    agent: NearbyFacilitiesAgent = Depends(get_nearby_agent),
) -> NearbyResponse:
    """다중 페이지 병원 리포트 (aggregate)."""
    request_id = str(uuid.uuid4())
    logger.info(
        "nearby/hospitals/report request_id=%s lat=%s lng=%s radius=%s max_pages=%d",
        request_id, lat, lng, radius_km, max_pages,
    )
    inp = NearbyReportInput(
        session_id=session_id or f"nearby-{request_id[:8]}",
        request_id=request_id,
        entity_type="hospital",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        num_of_rows=num_of_rows,
        max_pages=max_pages,
    )
    try:
        return await agent.report(inp)
    except Exception as exc:
        logger.error("nearby/hospitals/report failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="HIRA upstream failure") from exc


# ── /ai/nearby/pharmacies ────────────────────────────────────────────


@router.get("/pharmacies", response_model=NearbyResponse)
async def search_pharmacies(
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lng: float | None = Query(default=None, ge=-180.0, le=180.0),
    radius_km: float | None = Query(default=None, ge=0.0, le=100.0),
    name: str | None = Query(default=None, description="약국명 검색어 (yadmNm)"),
    sido_code: str | None = Query(default=None),
    sggu_code: str | None = Query(default=None),
    page_no: int = Query(default=1, ge=1),
    num_of_rows: int = Query(default=20, ge=1, le=1000),
    session_id: str | None = Query(default=None),
    agent: NearbyFacilitiesAgent = Depends(get_nearby_agent),
) -> NearbyResponse:
    """단일 페이지 약국 검색."""
    request_id = str(uuid.uuid4())
    logger.info(
        "nearby/pharmacies request_id=%s lat=%s lng=%s radius=%s page=%d rows=%d",
        request_id, lat, lng, radius_km, page_no, num_of_rows,
    )

    inp = NearbySearchInput(
        session_id=session_id or f"nearby-{request_id[:8]}",
        request_id=request_id,
        entity_type="pharmacy",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        name=name,
        sido_code=sido_code,
        sggu_code=sggu_code,
        page_no=page_no,
        num_of_rows=num_of_rows,
    )
    try:
        return await agent.search(inp)
    except Exception as exc:
        logger.error("nearby/pharmacies failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="HIRA upstream failure") from exc


@router.get("/pharmacies/report", response_model=NearbyResponse)
async def report_pharmacies(
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lng: float | None = Query(default=None, ge=-180.0, le=180.0),
    radius_km: float | None = Query(default=None, ge=0.0, le=100.0),
    num_of_rows: int = Query(default=1000, ge=1, le=1000),
    max_pages: int = Query(default=10, ge=1, le=100),
    session_id: str | None = Query(default=None),
    agent: NearbyFacilitiesAgent = Depends(get_nearby_agent),
) -> NearbyResponse:
    """다중 페이지 약국 리포트 (aggregate)."""
    request_id = str(uuid.uuid4())
    logger.info(
        "nearby/pharmacies/report request_id=%s lat=%s lng=%s radius=%s max_pages=%d",
        request_id, lat, lng, radius_km, max_pages,
    )
    inp = NearbyReportInput(
        session_id=session_id or f"nearby-{request_id[:8]}",
        request_id=request_id,
        entity_type="pharmacy",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        num_of_rows=num_of_rows,
        max_pages=max_pages,
    )
    try:
        return await agent.report(inp)
    except Exception as exc:
        logger.error("nearby/pharmacies/report failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="HIRA upstream failure") from exc


# ── /ai/nearby/ui — Kakao Map 데모 페이지 ────────────────────────────

_PERSONAS_JSON = json.dumps([
    {"id": "VP-001", "name": "김서연", "profile": "28F 초진 경증 · 마포구",
     "address": "서울특별시 마포구 월드컵북로 400", "lat": 37.5807, "lng": 126.8898},
    {"id": "VP-002", "name": "이준호", "profile": "35M 재진 경증 · 판교",
     "address": "경기도 성남시 분당구 판교역로 235", "lat": 37.4020, "lng": 127.1087},
    {"id": "VP-003", "name": "박민수", "profile": "42M 초진 중증 · 관악구",
     "address": "서울특별시 관악구 관악로 145", "lat": 37.4782, "lng": 126.9515},
    {"id": "VP-004", "name": "최하은", "profile": "29F 재진 중증 · 강서구",
     "address": "서울특별시 강서구 화곡로 302", "lat": 37.5510, "lng": 126.8495},
], ensure_ascii=False)


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def nearby_ui() -> HTMLResponse:
    """Kakao Map 데모 페이지 — 페르소나 위치 기반 병원·약국 검색 시각화."""
    settings = get_settings()
    js_key = settings.kakao_map_javascript_key
    if not js_key:
        return HTMLResponse(
            "<h1>KAKAO_MAP_JAVASCRIPT_KEY not configured</h1>"
            "<p>Set KAKAO_JS_KEY_ENCODED in .env and restart.</p>",
            status_code=500,
        )

    html = _NEARBY_UI_TEMPLATE.replace("{{JS_KEY}}", js_key).replace(
        "{{PERSONAS_JSON}}", _PERSONAS_JSON
    )
    return HTMLResponse(content=html, status_code=200)


_NEARBY_UI_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>Neuro-Sync — 근처 병원·약국</title>
  <style>
    :root { --hosp: #e53935; --pharm: #43a047; --user: #1e88e5; --bg: #fafafa; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: #222; }
    #app { display: flex; height: 100vh; }
    #sidebar { width: 360px; overflow-y: auto; border-right: 1px solid #ddd; background: #fff; }
    #map { flex: 1; }
    .controls { padding: 14px; border-bottom: 1px solid #eee; background: #fff; position: sticky; top: 0; z-index: 10; }
    .controls h1 { margin: 0 0 10px 0; font-size: 16px; }
    .row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; font-size: 13px; }
    .row label { display: flex; align-items: center; gap: 4px; }
    select, input[type=number] { padding: 4px 6px; font-size: 13px; }
    .persona-info { font-size: 11px; color: #666; margin-top: 4px; }
    button#search {
      width: 100%; padding: 8px; margin-top: 6px; background: #1976d2; color: #fff;
      border: 0; border-radius: 4px; cursor: pointer; font-size: 14px;
    }
    button#search:hover { background: #1565c0; }
    button#search:disabled { background: #bbb; }
    #status { padding: 8px 14px; font-size: 12px; color: #666; background: #f5f5f5; border-bottom: 1px solid #eee; }
    .place {
      padding: 10px 14px; border-bottom: 1px solid #eee; cursor: pointer;
      display: block; text-decoration: none; color: inherit;
    }
    .place:hover { background: #f0f7ff; }
    .place.selected { background: #e3f2fd; border-left: 3px solid #1976d2; }
    .badge {
      display: inline-block; padding: 1px 6px; border-radius: 3px;
      font-size: 10px; margin-right: 4px; font-weight: bold;
    }
    .badge-hosp { background: #ffcdd2; color: #b71c1c; }
    .badge-pharm { background: #c8e6c9; color: #1b5e20; }
    .distance { color: #666; font-size: 11px; float: right; margin-top: 2px; }
    .place-name { font-weight: 500; margin: 2px 0; }
    .place-addr { font-size: 11px; color: #666; }
    .place-phone { font-size: 11px; color: #1976d2; }
  </style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div class="controls">
      <h1>🏥 근처 병원·약국 검색</h1>
      <div class="row">
        <label>페르소나:
          <select id="persona"></select>
        </label>
      </div>
      <div class="persona-info" id="persona-info"></div>
      <div class="row">
        <label>반경(km): <input id="radius" type="number" value="2" min="0.1" max="20" step="0.5"></label>
        <label>개수: <input id="count" type="number" value="20" min="1" max="100"></label>
      </div>
      <div class="row">
        <label><input type="checkbox" id="show-hospitals" checked> 병원</label>
        <label><input type="checkbox" id="show-pharmacies" checked> 약국</label>
      </div>
      <div class="row" style="background:#fff3e0;padding:6px 8px;border-radius:4px;">
        <label style="font-weight:500;color:#e65100;">
          <input type="checkbox" id="psychiatric-only"> 🧠 정신건강의학과만 (dgsbjtCd=03)
        </label>
      </div>
      <button id="search">검색</button>
    </div>
    <div id="status">준비됨</div>
    <div id="places"></div>
  </div>
  <div id="map"></div>
</div>

<script>
  const PERSONAS = {{PERSONAS_JSON}};
  const state = {
    map: null,
    markers: [],           // {marker, data, kind}
    userMarker: null,
    infoWindow: null,
    selectedId: null,
  };

  function el(id) { return document.getElementById(id); }

  function setStatus(msg) { el('status').textContent = msg; }

  function initPersonas() {
    const sel = el('persona');
    PERSONAS.forEach((p, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = `${p.id} · ${p.name}`;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', () => updatePersonaInfo());
    updatePersonaInfo();
  }

  function updatePersonaInfo() {
    const p = PERSONAS[el('persona').value];
    el('persona-info').textContent = `${p.profile} — ${p.address}`;
  }

  function initMap() {
    kakao.maps.load(() => {
      const p = PERSONAS[el('persona').value];
      state.map = new kakao.maps.Map(el('map'), {
        center: new kakao.maps.LatLng(p.lat, p.lng),
        level: 5,
      });
      state.infoWindow = new kakao.maps.InfoWindow({ removable: true });
      renderUserMarker(p.lat, p.lng);
      setStatus('지도 준비됨. "검색"을 눌러주세요.');
      el('search').disabled = false;
    });
  }

  function renderUserMarker(lat, lng) {
    if (state.userMarker) state.userMarker.setMap(null);
    // 파란 원형 marker for user location
    const svg = 'data:image/svg+xml;utf8,' + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30">' +
      '<circle cx="15" cy="15" r="10" fill="#1e88e5" stroke="#fff" stroke-width="3"/>' +
      '</svg>'
    );
    state.userMarker = new kakao.maps.Marker({
      map: state.map,
      position: new kakao.maps.LatLng(lat, lng),
      image: new kakao.maps.MarkerImage(svg, new kakao.maps.Size(30, 30)),
      zIndex: 100,
    });
  }

  function clearMarkers() {
    state.markers.forEach(m => m.marker.setMap(null));
    state.markers = [];
    el('places').innerHTML = '';
    if (state.infoWindow) state.infoWindow.close();
  }

  function createColoredMarker(lat, lng, color, letter) {
    const svg = 'data:image/svg+xml;utf8,' + encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="34">
        <path d="M14 0 C 6 0 0 6 0 14 C 0 24 14 34 14 34 C 14 34 28 24 28 14 C 28 6 22 0 14 0 Z"
              fill="${color}" stroke="#fff" stroke-width="2"/>
        <text x="14" y="18" font-size="12" font-weight="bold" font-family="sans-serif"
              text-anchor="middle" fill="#fff">${letter}</text>
      </svg>`
    );
    return new kakao.maps.Marker({
      position: new kakao.maps.LatLng(lat, lng),
      image: new kakao.maps.MarkerImage(svg, new kakao.maps.Size(28, 34)),
    });
  }

  function renderPlace(place, kind) {
    const div = document.createElement('a');
    div.href = '#';
    div.className = 'place';
    div.dataset.id = place.id;
    const badge = kind === 'hospital'
      ? '<span class="badge badge-hosp">병원</span>'
      : '<span class="badge badge-pharm">약국</span>';
    const type = place.type_name ? ` <small style="color:#888">(${place.type_name})</small>` : '';
    const dist = place.distance_km != null ? `<span class="distance">${place.distance_km.toFixed(2)}km</span>` : '';
    div.innerHTML =
      `${badge}${type}${dist}` +
      `<div class="place-name">${place.name || '(이름 없음)'}</div>` +
      `<div class="place-addr">${place.address || ''}</div>` +
      (place.phone ? `<div class="place-phone">📞 ${place.phone}</div>` : '');
    div.addEventListener('click', (e) => {
      e.preventDefault();
      selectPlace(place.id);
    });
    return div;
  }

  function selectPlace(id) {
    state.selectedId = id;
    document.querySelectorAll('.place').forEach(el => {
      el.classList.toggle('selected', el.dataset.id === id);
      if (el.dataset.id === id) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
    const m = state.markers.find(x => x.data.id === id);
    if (!m) return;
    state.map.panTo(m.marker.getPosition());
    openInfoWindow(m);
  }

  function openInfoWindow(m) {
    const place = m.data;
    const dirUrl = `https://map.kakao.com/link/to/${encodeURIComponent(place.name)},${place.lat},${place.lng}`;
    const mapUrl = `https://map.kakao.com/link/map/${encodeURIComponent(place.name)},${place.lat},${place.lng}`;
    const html =
      `<div style="padding:10px 12px;min-width:220px;font-size:13px;line-height:1.5">
        <strong>${place.name}</strong><br>
        ${place.type_name ? `<small style="color:#888">${place.type_name}</small><br>` : ''}
        ${place.address}<br>
        ${place.phone ? `📞 ${place.phone}<br>` : ''}
        <div style="margin-top:6px;">
          <a href="${dirUrl}" target="_blank" style="margin-right:8px;">🚗 길찾기</a>
          <a href="${mapUrl}" target="_blank">🗺️ 카카오맵</a>
        </div>
      </div>`;
    state.infoWindow.setContent(html);
    state.infoWindow.open(state.map, m.marker);
  }

  async function search() {
    const p = PERSONAS[el('persona').value];
    const radius = parseFloat(el('radius').value);
    const count = parseInt(el('count').value, 10);
    const wantH = el('show-hospitals').checked;
    const wantP = el('show-pharmacies').checked;
    const psychOnly = el('psychiatric-only').checked;

    if (!wantH && !wantP) {
      setStatus('병원 또는 약국을 하나 이상 선택하세요.');
      return;
    }

    // 정신과 전용 모드 시 약국은 표시하지만 병원은 subject_code=03 필터 적용
    el('search').disabled = true;
    const psychTag = psychOnly ? ' [🧠 정신건강의학과만]' : '';
    setStatus(`${p.name} 위치 기준 ${radius}km 반경 검색 중...${psychTag}`);
    clearMarkers();
    state.map.setCenter(new kakao.maps.LatLng(p.lat, p.lng));
    renderUserMarker(p.lat, p.lng);

    const bounds = new kakao.maps.LatLngBounds();
    bounds.extend(new kakao.maps.LatLng(p.lat, p.lng));
    const listEl = el('places');
    let totalH = 0, totalP = 0;

    try {
      const paramsBase = new URLSearchParams({
        lat: p.lat, lng: p.lng, radius_km: radius, num_of_rows: count,
      });
      const paramsHosp = new URLSearchParams(paramsBase);
      if (psychOnly) paramsHosp.set('subject_code', '03');  // 정신건강의학과
      const paramsPharm = new URLSearchParams(paramsBase);
      if (wantH) {
        const r = await fetch(`/ai/nearby/hospitals?${paramsHosp}`);
        if (!r.ok) throw new Error(`hospitals HTTP ${r.status}`);
        const data = await r.json();
        totalH = data.sources?.hospital?.total_count || 0;
        data.map.markers.forEach(mk => {
          const marker = createColoredMarker(mk.lat, mk.lng, '#e53935', 'H');
          marker.setMap(state.map);
          const placeData = data.places.find(pl => pl.id === mk.id) || mk;
          kakao.maps.event.addListener(marker, 'click', () => selectPlace(placeData.id));
          state.markers.push({ marker, data: placeData, kind: 'hospital' });
          bounds.extend(marker.getPosition());
        });
        data.places.forEach(pl => listEl.appendChild(renderPlace(pl, 'hospital')));
      }
      if (wantP) {
        const r = await fetch(`/ai/nearby/pharmacies?${paramsPharm}`);
        if (!r.ok) throw new Error(`pharmacies HTTP ${r.status}`);
        const data = await r.json();
        totalP = data.sources?.pharmacy?.total_count || 0;
        data.map.markers.forEach(mk => {
          const marker = createColoredMarker(mk.lat, mk.lng, '#43a047', 'P');
          marker.setMap(state.map);
          const placeData = data.places.find(pl => pl.id === mk.id) || mk;
          kakao.maps.event.addListener(marker, 'click', () => selectPlace(placeData.id));
          state.markers.push({ marker, data: placeData, kind: 'pharmacy' });
          bounds.extend(marker.getPosition());
        });
        data.places.forEach(pl => listEl.appendChild(renderPlace(pl, 'pharmacy')));
      }

      if (state.markers.length > 0) state.map.setBounds(bounds, 40, 40, 40, 40);
      const psychLabel = psychOnly ? '정신과' : '병원';
      setStatus(`${psychLabel} ${state.markers.filter(m => m.kind === 'hospital').length}/${totalH} · 약국 ${state.markers.filter(m => m.kind === 'pharmacy').length}/${totalP}개 (${p.name})`);
    } catch (exc) {
      setStatus('검색 실패: ' + exc.message);
      console.error(exc);
    } finally {
      el('search').disabled = false;
    }
  }

  // Load Kakao SDK dynamically
  function loadSdk() {
    const s = document.createElement('script');
    s.src = 'https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&libraries=clusterer&appkey={{JS_KEY}}';
    s.onload = () => initMap();
    s.onerror = () => setStatus('Kakao SDK 로드 실패 (도메인 등록 확인 필요)');
    document.head.appendChild(s);
  }

  initPersonas();
  el('search').disabled = true;
  el('search').addEventListener('click', search);
  el('persona').addEventListener('change', () => {
    const p = PERSONAS[el('persona').value];
    if (state.map) {
      state.map.setCenter(new kakao.maps.LatLng(p.lat, p.lng));
      renderUserMarker(p.lat, p.lng);
    }
  });
  loadSdk();
</script>
</body>
</html>
"""
