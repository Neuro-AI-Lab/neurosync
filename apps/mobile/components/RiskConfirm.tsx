/**
 * 공통 위험 확인 창 (v3 FR-042/043).
 *
 * 위험 감지 시 강제 전환 대신 사용자의 명시적 선택을 받는다:
 * [도움 받기] → /emergency 진입 · [괜찮아요] → 원래 화면 복귀.
 * 대화 중에는 모달(RiskConfirmModal), 문진 중에는 인라인 카드(RiskConfirmCard)로
 * 동일 콘텐츠를 렌더한다. 클라이언트 전용 — 에이전트 메시지 수정 불필요.
 *
 * NFR(v3-1): 네트워크 상태와 무관하게 즉시 렌더 (로컬 콘텐츠만 사용).
 */

import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { Phone } from "../lib/icons";
import { colors } from "../lib/tokens";

type RiskConfirmProps = {
  onHelp: () => void;
  onDismiss: () => void;
  /** 문진 카드용 대체 문구 (기본은 대화용). */
  body?: string;
  dismissLabel?: string;
};

const DEFAULT_BODY =
  "말씀해 주셔서 고마워요. 원하시면 지금 바로 도움을 받을 수 있어요.\n어떻게 할지는 직접 선택하실 수 있어요.";

function RiskConfirmContent({
  onHelp,
  onDismiss,
  body = DEFAULT_BODY,
  dismissLabel = "괜찮아요, 계속할게요",
}: RiskConfirmProps) {
  return (
    <View accessibilityLiveRegion="assertive">
      <View style={styles.eyebrowRow}>
        <View style={styles.dot} />
        <Text style={styles.eyebrow}>잠시 확인할게요</Text>
      </View>
      <Text style={styles.title}>지금, 마음이 많이 힘드신가요?</Text>
      <Text style={styles.body}>{body}</Text>

      <Pressable
        onPress={onHelp}
        accessibilityRole="button"
        accessibilityLabel="도움 받기"
        style={({ pressed }) => [styles.helpBtn, { opacity: pressed ? 0.85 : 1 }]}
      >
        <Phone size={15} color="#FFFFFF" strokeWidth={1.9} />
        <Text style={styles.helpText}>도움 받기</Text>
      </Pressable>
      <Pressable
        onPress={onDismiss}
        accessibilityRole="button"
        accessibilityLabel={dismissLabel}
        style={({ pressed }) => [styles.dismissBtn, { opacity: pressed ? 0.7 : 1 }]}
      >
        <Text style={styles.dismissText}>{dismissLabel}</Text>
      </Pressable>
    </View>
  );
}

/** 대화 중 — 모달 표시 (FR-042). 배경 탭으로 닫히지 않는다 — 명시적 선택만. */
export function RiskConfirmModal({
  visible,
  ...props
}: RiskConfirmProps & { visible: boolean }) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={props.onDismiss}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <RiskConfirmContent {...props} />
        </View>
      </View>
    </Modal>
  );
}

/** 문진 중 — 인라인 카드 (FR-043). 설문 흐름을 중단하지 않는다. */
export function RiskConfirmCard(props: RiskConfirmProps) {
  return (
    <View style={styles.card}>
      <RiskConfirmContent
        body={
          props.body ??
          "응답해 주셔서 고마워요. 지금 도움이 필요하시면 바로 연결해 드릴게요.\n설문은 그대로 이어집니다."
        }
        dismissLabel={props.dismissLabel ?? "괜찮아요, 계속할게요"}
        onHelp={props.onHelp}
        onDismiss={props.onDismiss}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(18,18,16,0.45)",
    justifyContent: "flex-end",
    padding: 16,
  },
  sheet: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    padding: 20,
    paddingBottom: 24,
  },
  card: {
    borderWidth: 1,
    borderColor: colors.dangerLine,
    backgroundColor: colors.dangerSoft,
    borderRadius: 16,
    padding: 16,
  },
  eyebrowRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.danger },
  eyebrow: { color: colors.dangerInk, fontSize: 11, fontWeight: "700", letterSpacing: 0.3 },
  title: {
    marginTop: 10,
    fontSize: 19,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.4,
    lineHeight: 25,
  },
  body: { marginTop: 8, fontSize: 13.5, color: colors.ink2, lineHeight: 20 },
  helpBtn: {
    marginTop: 16,
    height: 50,
    borderRadius: 14,
    backgroundColor: colors.danger,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  helpText: { color: "#FFFFFF", fontSize: 15, fontWeight: "600" },
  dismissBtn: {
    marginTop: 8,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  dismissText: { color: colors.muted, fontSize: 14, fontWeight: "500" },
});
