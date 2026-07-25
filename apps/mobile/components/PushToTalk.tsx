import {
  AudioQuality,
  IOSOutputFormat,
  RecordingOptions,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";
import * as Haptics from "expo-haptics";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { APIException, transcribeAudio } from "../lib/api";
import { Mic, Stop } from "../lib/icons";
import { colors } from "../lib/tokens";

/**
 * Push-to-Talk mic (FR-033/035/037). Tap to start, tap to stop → transcribe.
 * The result fills the chat input via `onTranscript` — it is NEVER auto-sent
 * (FR-035). Failures (consent / low confidence / mic perm) fall back to the
 * keyboard with a short notice (FR-037).
 *
 * Records 16kHz mono PCM WAV (backend `encoding=pcm16`). iOS LinearPCM is the
 * verified path; Android WAV via expo-audio is best-effort (the backend would
 * reject a non-WAV container — track per the chosen demo platform).
 *
 * Migrated expo-av → expo-audio for Expo SDK 54 (expo-av was removed): the
 * recorder now comes from the `useAudioRecorder` hook instead of the imperative
 * `Audio.Recording.createAsync`.
 */
const MIN_MS = 700;

const WAV_OPTIONS: RecordingOptions = {
  extension: ".wav",
  sampleRate: 16000,
  numberOfChannels: 1,
  bitRate: 256000,
  isMeteringEnabled: false,
  android: {
    outputFormat: "default",
    audioEncoder: "default",
  },
  ios: {
    outputFormat: IOSOutputFormat.LINEARPCM,
    audioQuality: AudioQuality.HIGH,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: { mimeType: "audio/webm", bitsPerSecond: 128000 },
};

type Status = "idle" | "recording" | "processing";

type Props = {
  token: string | null;
  sessionId: string | null;
  disabled?: boolean;
  onTranscript: (text: string) => void;
  /** User-facing notice (keyboard fallback). reason ∈ permission/too_short/low_confidence/consent/error */
  onNotice: (reason: string, message: string) => void;
};

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function PushToTalk({ token, sessionId, disabled, onTranscript, onNotice }: Props) {
  const recorder = useAudioRecorder(WAV_OPTIONS);
  const [status, setStatus] = useState<Status>("idle");
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const canceledRef = useRef(false);
  // 녹음 여부를 JS 쪽에서 추적한다. 언마운트 시 recorder.isRecording(네이티브
  // shared object) 접근은 객체가 이미 해제됐으면 NativeSharedObjectNotFound로
  // 터지므로, 정리 판단은 이 ref로만 한다.
  const recordingRef = useRef(false);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      clearTimer();
      // 녹음 중일 때만 최선의 정리. idle 언마운트(대부분)에서는 네이티브 객체를
      // 아예 건드리지 않는다. 녹음 중이어도 네이티브 객체가 이미 해제됐을 수
      // 있으므로 stop() 호출 자체를 try/catch로 감싼다.
      if (recordingRef.current) {
        recordingRef.current = false;
        try {
          void recorder.stop().catch(() => undefined);
        } catch {
          // NativeSharedObjectNotFound 등 — 이미 정리됨. 무시.
        }
      }
    };
    // recorder identity is stable for the component's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const start = async () => {
    if (disabled || status !== "idle" || !token || !sessionId) return;
    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        onNotice("permission", "마이크 권한이 필요해요. 설정에서 허용해 주세요.");
        return;
      }
      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      await recorder.prepareToRecordAsync(WAV_OPTIONS);
      recorder.record();
      recordingRef.current = true;
      canceledRef.current = false;
      startRef.current = Date.now();
      setElapsed(0);
      setStatus("recording");
      timerRef.current = setInterval(
        () => setElapsed(Date.now() - startRef.current),
        200,
      );
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch {
      clearTimer(); // 타이머가 이미 걸렸다면 정리 — idle 컴포넌트에 stray tick 방지
      setStatus("idle");
      onNotice("error", "녹음을 시작할 수 없어요. 키보드로 입력해 주세요.");
    }
  };

  const stopRecording = async (): Promise<string | null> => {
    clearTimer();
    recordingRef.current = false;
    try {
      await recorder.stop();
      return recorder.uri;
    } catch {
      return null;
    }
  };

  const cancel = async () => {
    canceledRef.current = true;
    await stopRecording();
    setStatus("idle");
    setElapsed(0);
  };

  const stopAndTranscribe = async () => {
    if (status !== "recording" || !token || !sessionId) return;
    const ms = Date.now() - startRef.current;
    setStatus("processing");
    const uri = await stopRecording();
    if (canceledRef.current) return;
    if (!uri || ms < MIN_MS) {
      setStatus("idle");
      setElapsed(0);
      if (ms < MIN_MS) onNotice("too_short", "너무 짧아요. 조금 더 길게 말씀해 주세요.");
      return;
    }
    try {
      const result = await transcribeAudio(token, sessionId, {
        uri,
        encoding: "pcm16",
        sampleRateHz: 16000,
      });
      onTranscript(result.text);
    } catch (e) {
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      if (code === "VOICE_CONSENT_REQUIRED") {
        onNotice("consent", "음성 입력 동의가 필요해요. 설정에서 켜주세요.");
      } else if (code === "STT_LOW_CONFIDENCE") {
        onNotice("low_confidence", "잘 들리지 않았어요. 다시 말씀하거나 키보드로 입력해 주세요.");
      } else {
        onNotice("error", `음성 인식에 실패했어요. 키보드로 입력해 주세요 (${code}).`);
      }
    } finally {
      setStatus("idle");
      setElapsed(0);
    }
  };

  const onPress = () => {
    if (status === "idle") void start();
    else if (status === "recording") void stopAndTranscribe();
  };

  const recording = status === "recording";

  return (
    <View>
      {recording ? (
        <View style={styles.pill}>
          <View style={styles.dot} />
          <Text style={styles.timer}>{fmt(elapsed)}</Text>
          <Text style={styles.pillLabel}>듣고 있어요 · 다시 누르면 인식</Text>
          <Pressable onPress={() => void cancel()} hitSlop={8} accessibilityRole="button">
            <Text style={styles.cancel}>취소</Text>
          </Pressable>
        </View>
      ) : null}

      <Pressable
        onPress={onPress}
        disabled={disabled || status === "processing" || !token || !sessionId}
        accessibilityRole="button"
        accessibilityLabel={recording ? "녹음 정지 및 인식" : "음성 입력 시작"}
        style={({ pressed }) => [
          styles.mic,
          recording && styles.micActive,
          { opacity: disabled || status === "processing" ? 0.4 : pressed ? 0.7 : 1 },
        ]}
      >
        {status === "processing" ? (
          <ActivityIndicator size="small" color={colors.muted} />
        ) : recording ? (
          <Stop size={15} color="#FFFFFF" />
        ) : (
          <Mic size={17} color={colors.ink} />
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  mic: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.fill,
  },
  micActive: { backgroundColor: colors.danger },
  pill: {
    position: "absolute",
    bottom: "100%",
    right: 0,
    marginBottom: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 14,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.dangerLine,
    width: 260,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
  },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.danger },
  timer: { fontSize: 14, color: colors.ink, fontWeight: "500", fontVariant: ["tabular-nums"] },
  pillLabel: { flex: 1, color: colors.muted, fontSize: 11.5 },
  cancel: { color: colors.danger, fontSize: 12.5, fontWeight: "600" },
});
