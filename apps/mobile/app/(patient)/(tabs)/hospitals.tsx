/**
 * S-11 `/hospitals` — 근처 정신건강의학과 지도 (FR-049).
 *
 * 위치 권한을 받아 카카오맵(플랫폼 프록시가 렌더한 HTML)을 WebView로 띄운다.
 * react-native-webview / expo-location 모두 Expo Go에 내장돼 있어 네이티브
 * 빌드가 필요 없다. 지도 로드 실패·권한 거부 시에도 119 연결은 항상 열어둔다.
 *
 * 위기 상태(CTRS 1–2)에서는 목록보다 119/109 안내를 우선한다 — 이 화면은
 * 항상 응급 배너를 상단에 둔다.
 */

import * as Location from "expo-location";
import { useEffect, useState } from "react";
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";

import { Hospital, Phone } from "../../../lib/icons";
import { hospitalsMapUrl } from "../../../lib/config";
import { colors } from "../../../lib/tokens";

// 위치 권한 거부 시 기본 중심 — 서울시청. 지도가 비어 보이지 않게 한다.
const SEOUL = { lat: 37.5665, lng: 126.978 };

type Phase = "locating" | "ready" | "denied" | "error";

export default function HospitalsScreen() {
  const insets = useSafeAreaInsets();
  const [phase, setPhase] = useState<Phase>("locating");
  const [coords, setCoords] = useState(SEOUL);
  const [webError, setWebError] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (!alive) return;
        if (status !== "granted") {
          // 거부해도 서울 중심으로 지도는 보여준다.
          setPhase("denied");
          return;
        }
        const loc = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        if (!alive) return;
        setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
        setPhase("ready");
      } catch {
        if (alive) setPhase("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const showMap = phase === "ready" || phase === "denied";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Text style={[styles.largeTitle, { paddingTop: insets.top + 8 }]}>병원 찾기</Text>

      {/* 응급 배너 — 항상 상단 고정 */}
      <Pressable
        style={styles.emergency}
        onPress={() => Linking.openURL("tel:119")}
        accessibilityRole="button"
        accessibilityLabel="119 전화 걸기"
      >
        <Phone size={16} color={colors.dangerInk} strokeWidth={1.9} />
        <Text style={styles.emergencyText}>응급 상황이라면 지금 119</Text>
        <Text style={styles.emergencyCta}>전화</Text>
      </Pressable>

      {phase === "denied" ? (
        <View style={styles.notice}>
          <Text style={styles.noticeText}>
            위치 권한을 허용하면 내 주변 병원을 볼 수 있어요. 지금은 서울 중심으로 보여드려요.
          </Text>
        </View>
      ) : null}

      <View style={styles.mapWrap}>
        {phase === "locating" ? (
          <View style={styles.center}>
            <ActivityIndicator color={colors.ink} />
            <Text style={styles.centerText}>내 위치를 확인하고 있어요…</Text>
          </View>
        ) : null}

        {showMap && !webError ? (
          <WebView
            source={{ uri: hospitalsMapUrl(coords.lat, coords.lng) }}
            style={styles.web}
            onError={() => setWebError(true)}
            onHttpError={() => setWebError(true)}
            startInLoadingState
            renderLoading={() => (
              <View style={styles.center}>
                <ActivityIndicator color={colors.ink} />
              </View>
            )}
            originWhitelist={["*"]}
            javaScriptEnabled
            domStorageEnabled
          />
        ) : null}

        {phase === "error" || webError ? (
          <View style={styles.center}>
            <View style={styles.iconBox}>
              <Hospital size={36} color={colors.muted} strokeWidth={1.5} />
            </View>
            <Text style={styles.lead}>지도를 불러오지 못했어요</Text>
            <Text style={styles.note}>
              인터넷 연결을 확인해 주세요. 응급 시에는 위 119를 이용하세요.
            </Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  largeTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.9,
    paddingHorizontal: 20,
    paddingBottom: 6,
  },
  emergency: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginHorizontal: 20,
    marginBottom: 10,
    paddingHorizontal: 15,
    paddingVertical: 12,
    borderRadius: 14,
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.dangerLine,
  },
  emergencyText: { flex: 1, fontSize: 14, fontWeight: "600", color: colors.dangerInk },
  emergencyCta: { fontSize: 13.5, fontWeight: "700", color: colors.dangerInk },
  notice: {
    marginHorizontal: 20,
    marginBottom: 10,
    padding: 12,
    borderRadius: 12,
    backgroundColor: colors.fill,
  },
  noticeText: { fontSize: 12.5, color: colors.muted, lineHeight: 18 },
  mapWrap: { flex: 1, overflow: "hidden" },
  web: { flex: 1, backgroundColor: colors.fill },
  center: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 32,
    backgroundColor: colors.surface,
  },
  centerText: { fontSize: 13, color: colors.muted },
  iconBox: {
    width: 88,
    height: 88,
    borderRadius: 20,
    backgroundColor: colors.fill,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 6,
  },
  lead: { fontSize: 16, fontWeight: "600", color: colors.ink },
  note: { fontSize: 13, color: colors.muted, textAlign: "center", lineHeight: 19 },
});
