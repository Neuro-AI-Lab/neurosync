"""GET /api/v1/nearby/hospitals/map — 카카오맵 HTML 렌더 (FR-049).

ADR-041: 병원 검색 데이터는 플랫폼(apps/api)이 직접 조회한다(ai-server 미경유).
데이터 조회는 `src.services.hospital_finder`(Kakao Local 키워드 검색)가 담당하고,
여기서 그 좌표로 카카오맵 HTML을 그린다. 카카오 JS 키는 플랫폼 설정
(KAKAO_JS_KEY_ENCODED)에 둔다.

앱은 이 URL을 react-native-webview로 로드한다. 지도 데이터(병원 위치)는 공개
정보라 인증을 요구하지 않는다 — 위기 상황에 로그인 없이도 근처 병원을 볼 수
있어야 한다.

우아한 저하:
- 카카오 JS 키 없음 → 안내 화면(200)
- 병원 검색 실패(REST 키 없음 등) → 내 위치만 있는 빈 지도(200)
어떤 경우에도 500을 내지 않는다 — WebView가 500을 받으면 에러 화면만 뜬다.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from src.core.config import Settings, get_settings
from src.services.hospital_finder import find_psychiatry_hospitals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nearby", tags=["nearby"])


@router.get("/hospitals/map", response_class=HTMLResponse)
async def hospitals_map(
    lat: Annotated[float, Query(ge=-90.0, le=90.0)],
    lng: Annotated[float, Query(ge=-180.0, le=180.0)],
    settings: Annotated[Settings, Depends(get_settings)],
    radius_km: Annotated[float, Query(ge=0.0, le=20.0)] = 5.0,
) -> HTMLResponse:
    js_key = settings.kakao_map_javascript_key
    if not js_key:
        return HTMLResponse(_KEY_MISSING_HTML, status_code=200)

    # ADR-041 정합: 플랫폼이 직접 Kakao Local로 근처 정신건강의학과를 조회한다.
    # 실패해도 빈 리스트를 돌려주므로 내 위치만 있는 지도로 우아하게 저하한다.
    places = await find_psychiatry_hospitals(
        lat=lat, lng=lng, radius_km=radius_km, settings=settings
    )

    html = (
        _MAP_TEMPLATE.replace("{{JS_KEY}}", js_key)
        .replace("{{USER_LAT}}", repr(lat))
        .replace("{{USER_LNG}}", repr(lng))
        .replace("{{PLACES_JSON}}", json.dumps(places, ensure_ascii=False))
    )
    return HTMLResponse(content=html, status_code=200)


_KEY_MISSING_HTML = (
    "<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<style>body{margin:0;font-family:-apple-system,sans-serif;display:flex;"
    "align-items:center;justify-content:center;height:100vh;color:#8C8C86;"
    "text-align:center;padding:24px}</style></head><body>"
    "<div><p style='font-size:15px'>지도를 불러올 수 없어요.</p>"
    "<p style='font-size:13px'>서버에 카카오 지도 키가 설정되지 않았어요.</p></div>"
    "</body></html>"
)


_MAP_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport"
        content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <style>
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    html, body { margin: 0; height: 100%;
      font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; }
    #map { width: 100%; height: 100%; background: #F3F3F1; }
    #status { position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
      background: rgba(18,18,16,.82); color: #fff; font-size: 13px; padding: 8px 14px;
      border-radius: 999px; z-index: 5; }
    #sheet { position: absolute; left: 12px; right: 12px; bottom: 14px; z-index: 6;
      background: #fff; border-radius: 18px; padding: 16px; transform: translateY(140%);
      transition: transform .22s cubic-bezier(.2,.8,.2,1);
      box-shadow: 0 12px 40px -12px rgba(15,15,10,.35); }
    #sheet.on { transform: translateY(0); }
    #sheet .nm { font-size: 17px; font-weight: 700; color: #121210; letter-spacing: -.3px; }
    #sheet .meta { font-size: 12.5px; color: #8C8C86; margin-top: 5px; line-height: 1.4; }
    #sheet .row { display: flex; gap: 8px; margin-top: 14px; }
    #sheet .btn { flex: 1; height: 46px; border-radius: 12px; display: flex; align-items: center;
      justify-content: center; gap: 6px; font-size: 14.5px; font-weight: 600;
      text-decoration: none; }
    #sheet .call { background: #F3F3F1; color: #121210; }
    #sheet .dir { background: #121210; color: #fff; }
    #sheet .close { position: absolute; top: 12px; right: 14px; color: #B3B3AD; font-size: 20px; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="status">지도를 불러오는 중…</div>
  <div id="sheet">
    <span class="close" onclick="hideSheet()">✕</span>
    <div class="nm" id="s-name"></div>
    <div class="meta" id="s-meta"></div>
    <div class="row">
      <a class="btn call" id="s-call">전화</a>
      <a class="btn dir" id="s-dir">길찾기</a>
    </div>
  </div>
<script>
  var USER = { lat: {{USER_LAT}}, lng: {{USER_LNG}} };
  var PLACES = {{PLACES_JSON}};
  var map;

  function setStatus(t) {
    var el = document.getElementById('status');
    if (!t) { el.style.display = 'none'; return; }
    el.style.display = 'block'; el.textContent = t;
  }
  function hideSheet() { document.getElementById('sheet').classList.remove('on'); }
  function showSheet(p) {
    document.getElementById('s-name').textContent = p.name;
    var meta = [];
    if (p.distance_km != null) meta.push(p.distance_km.toFixed(1) + 'km');
    if (p.type_name) meta.push(p.type_name);
    if (p.address) meta.push(p.address);
    document.getElementById('s-meta').textContent = meta.join(' · ');
    var call = document.getElementById('s-call');
    if (p.phone) {
      call.style.display = 'flex';
      call.href = 'tel:' + p.phone.replace(/[^0-9+]/g, '');
    } else { call.style.display = 'none'; }
    document.getElementById('s-dir').href =
      'https://map.kakao.com/link/to/' + encodeURIComponent(p.name) + ',' + p.lat + ',' + p.lng;
    document.getElementById('sheet').classList.add('on');
  }

  function initMap() {
    kakao.maps.load(function () {
      var center = new kakao.maps.LatLng(USER.lat, USER.lng);
      map = new kakao.maps.Map(document.getElementById('map'), { center: center, level: 5 });
      kakao.maps.event.addListener(map, 'click', hideSheet);

      new kakao.maps.Circle({
        center: center, radius: 90, strokeWeight: 2, strokeColor: '#1e88e5',
        strokeOpacity: .9, fillColor: '#1e88e5', fillOpacity: .35
      }).setMap(map);

      var bounds = new kakao.maps.LatLngBounds();
      bounds.extend(center);

      PLACES.forEach(function (p) {
        var pos = new kakao.maps.LatLng(p.lat, p.lng);
        var marker = new kakao.maps.Marker({ position: pos, map: map, title: p.name });
        kakao.maps.event.addListener(marker, 'click', function () { showSheet(p); });
        bounds.extend(pos);
      });

      if (PLACES.length) map.setBounds(bounds);
      setStatus(PLACES.length ? '' : '주변에 검색된 병원이 없어요');
    });
  }

  var s = document.createElement('script');
  s.src = 'https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&appkey={{JS_KEY}}';
  s.onload = initMap;
  s.onerror = function () { setStatus('지도 로드 실패 — 카카오 도메인 등록을 확인해 주세요'); };
  document.head.appendChild(s);
</script>
</body>
</html>
"""
